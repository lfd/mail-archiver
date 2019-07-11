#!/bin/bash

# mail-archiver - a simple maildir to public inbox (git) converter
#
# Copyright (c) OTH Regensburg, 2019
#
# Author:
#   Ralf Ramsauer <ralf.ramsauer@oth-regensburg.de>
#
# This work is licensed under the terms of the GNU GPL, version 2.  See
# the COPYING file in the top-level directory.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.

archives="./archives/"
index="./index"

# Check if an old ERROR is pending. Abort in that case.
if [ -f "ERROR" ]; then
	echo "Previous error occured. Please check the working directory"
	exit -1
fi

# Ensure every repo is on master, and not on detached heads.
git submodule foreach git co master

# Let the archiver run. If it fails, reset all archives to their upstream
# state. This preserves a consistent state in case of errors.
./archiver.py
if [ $? -ne 0 ]; then
	echo "Error during archival process. Reverting changes."
	git submodule foreach git reset --hard origin/master
	git checkout index
	touch ERROR
	exit -1
fi

# Pygit has left fragments, as it won't update the checked-out directories.
# Reset ALL modules inside archives (including non-submodules) to their master
for archive in ${archives}/*; do
	git -C $archive reset --hard
done

# Get the list of modifies archives (submodules only)
modified_archives=$(git status --short | grep "M archives" | awk '{ print $2 }')

# Now add the new stuff
git add index
git add $modified_archives
git commit -m "update public inboxes"

for d_archive in $modified_archives; do
	archive=$(basename $d_archive)
	git="git -C $d_archive"

	# Let's GC the repo first
	$git gc

	# We can easily push. There can not be submodules without a valid
	# remote. New repositories must be manually created. git status list
	# repos without a remote as untracked.

	# Note: ASSORTED archives are NOT stored on github.
	$git push
done

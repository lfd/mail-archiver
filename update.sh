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

gh_group='linux-mailinglist-archives'
uri_base="git@github.com:${gh_group}/"

gcli="$HOME/.gem/ruby/2.3.0/bin/gcli"

./archiver.py || exit -1
git add index
git commit -m "update index"

for i in $archives/*; do
	git -C $i gc
done

for d_archive in $archives/*; do
	archive=$(basename $d_archive)

	# Skip ASSORTED.*
	if [[ $archive = ASSORTED.* ]]; then
		continue
	fi

	git="git -C $d_archive"
	$git remote get-url origin > /dev/null 2>&1
	if [ $? -eq 0 ]; then
		$git push
	else
		echo Creating $archive
		uri="${uri_base}${archive}.git"
		echo $uri
		$gcli repo create ${gh_group}/$archive > /dev/null
		$git remote add origin $uri
		$git push --set-upstream origin master
	fi
done

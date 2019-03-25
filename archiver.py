#!/usr/bin/env python3

"""
mail-archiver - a simple maildir to public inbox (git) converter

Copyright (c) OTH Regensburg, 2019

Author:
  Ralf Ramsauer <ralf.ramsauer@oth-regensburg.de>

This work is licensed under the terms of the GNU GPL, version 2.  See
the COPYING file in the top-level directory.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.
"""

import dateparser
import datetime
import email
import glob
import os
import pygit2
import pytz
import re

from os.path import basename, dirname, expanduser, realpath, join
from tqdm import tqdm

d_maildir = '~/Mail'
d_public_inboxes = './archives'
f_index = './index'

r_assorted = 'ASSORTED'

list_id_regex = re.compile(r'.*<(.*)>.*', re.MULTILINE | re.DOTALL)
via_regex = re.compile(r'(.+) via .+')

d_maildir = realpath(expanduser(d_maildir))
ctn = {'cur', 'tmp', 'new'}


def find_dirs(dir):
    ret = set()
    dirs = glob.glob(join(dir, '*') + '/') + glob.glob(join(dir, '.*') + '/')
    dirs = {basename(dirname(x)) for x in dirs}

    if ctn.issubset(dirs):
        ret.add(dir)

    for subdir in dirs - ctn:
        ret |= find_dirs(join(dir, subdir))

    return ret


def parse_date(date):
    try:
        ret = email.utils.parsedate_to_datetime(date)
    except Exception:
        ret = None

    if not ret:
        try:
            ret = dateparser.parse(date)
        except Exception:
            ret = datetime.date.fromtimestamp(0)

    if not ret.tzinfo:
        ret = pytz.utc.localize(ret)

    return ret


def decode_header(header):
    try:
        tmp = email.header.decode_header(header)
        tmp = email.header.make_header(tmp)
        return str(tmp)
    except:
        return header


def load_mail(filename):
    with open(filename, 'rb') as fp:
        mail = email.message_from_binary_file(fp)

    return mail


def header_is_yes(header):
    if header is None:
        return False

    if header.lower() == 'yes':
        return True
    return False


class PublicInbox:
    AUTHOR_REGEX = re.compile(r'(.*)\s?<(.*)>')
    LIST_ID_REGEX = re.compile(r'.*<(.*)>.*', re.MULTILINE | re.DOTALL)

    def __init__(self, d_repo):
        self.list_name = basename(d_repo)
        self.repo = pygit2.Repository(d_repo)

    @staticmethod
    def create(d_repo):
        pygit2.init_repository(d_repo, bare=True)

        return PublicInbox(d_repo)

    @staticmethod
    def get_list_post_address(mail):
        list_post = mail['list-post']
        if list_post:
            list_post = PublicInbox.LIST_ID_REGEX.match(list_post).group(1)

        if not list_post:
            list_post = mail['x-mailing-list']
        if not list_post:
            list_post = mail['x-original-to']
        if not list_post:
            list_post = mail['sender']

        if not list_post:
            list_post = 'unknown@address.com'

        if list_post.startswith('mailto:'):
            list_post = list_post[len('mailto:'):]

        match = PublicInbox.LIST_ID_REGEX.match(list_post)
        if match:
            list_post = match.group(1)

        return list_post

    @staticmethod
    def get_author_name(mail):
        from_hdr = decode_header(mail['From'])
        from_hdr = from_hdr.replace('\n', '')

        author_name, author_email = email.utils.parseaddr(from_hdr)

        match = PublicInbox.AUTHOR_REGEX.match(author_name)
        if match:
            author_name = match.group(1).rstrip()

        author_name = author_name.strip('"')

        match = via_regex.match(author_name)
        if match:
            author_name = match.group(1)
            author_email = email.utils.parseaddr(mail['reply-to'])[1]

        if author_name == '':
            author_name = author_email

        if author_email == '':
            author_email = 'UNKNOWN@UNKNOWN.COM'

        date = parse_date(mail['Date'])
        time = int(date.timestamp())

        offset = date.utcoffset()
        if offset:
            offset = int(date.utcoffset().seconds / 60)
        else:
            offset = 0

        return pygit2.Signature(author_name, author_email, time, offset)

    def insert(self, filename, mail):
        author = PublicInbox.get_author_name(mail)
        list_post = PublicInbox.get_list_post_address(mail)

        committer = pygit2.Signature(self.list_name, list_post)
        message = decode_header(mail['Subject'] or '')

        blob = self.repo.create_blob_fromdisk(filename)
        treebuilder = self.repo.TreeBuilder()

        treebuilder.insert('m', blob, pygit2.GIT_FILEMODE_BLOB)
        tree = treebuilder.write()

        try:
            parents = [self.repo.head.target.hex]
        except:
            parents = []

        chash = self.repo.create_commit('refs/heads/master', author, committer,
                                        message, tree, parents)

        return chash.hex


d_maildirs = find_dirs(d_maildir)
public_inboxes = dict()

for d_public_inbox in glob.glob(join(d_public_inboxes, '*')):
    public_inboxes[basename(d_public_inbox)] = PublicInbox(d_public_inbox)

if os.path.isfile(f_index):
    with open(f_index, 'r') as f:
        index = f.read().split()
        index = set(index)
else:
    index = set()

worklist = list()

print('Searching for new mails')
for d_maildir in d_maildirs:
    print('Working on maildir %s' % d_maildir)
    for sub in ctn:
        dir = join(d_maildir, sub)
        files = {basename(x) for x in glob.glob(join(dir, '*'))}
        files = files - index
        print('  %u new files in %s' % (len(files), sub))

        for file in files:
            filename = join(dir, file)
            mail = load_mail(join(dir, filename))

            message_id = mail['message-id']
            if message_id is None:
                print('Skipping %s. Reason: No message-id header' % file)
                continue

            hdr_date = mail['date']
            if hdr_date is None:
                print('Warning, date not found for %s' % file)

            date = parse_date(hdr_date)
            worklist.append((date, filename))

# sort worklist by date
worklist.sort(key=lambda x: x[0])
worklist = [x[1] for x in worklist]

def process_mail(f_mail):
    mail = load_mail(f_mail)

    list_id = mail['list-id']
    if not list_id:
        #print('No list-id in %s' % filename)
        list_id = r_assorted
    else:
        list_id = list_id_regex.match(list_id).group(1)

    if header_is_yes(mail['x-no-archive']) or\
       header_is_yes(mail['x-list-administrivia']):
        #print('Found administrative mail')
        list_id = r_assorted

    if list_id not in public_inboxes:
        print('Creating Public Inbox %s' % list_id)
        public_inboxes[list_id] = PublicInbox.create(join(d_public_inboxes, list_id))

    public_inboxes[list_id].insert(f_mail, mail)
    index.add(basename(f_mail))


if len(worklist) == 0:
    print('Nothing to be done')
    quit(0)

print('Update inboxes')
for item in tqdm(worklist):
    process_mail(item)

print('Writing index')
with open(f_index, 'w') as f:
    for file in sorted(index):
        f.write(file + '\n')

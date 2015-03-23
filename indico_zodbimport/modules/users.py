# This file is part of Indico.
# Copyright (C) 2002 - 2015 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import re

from indico.core.db import db
from indico.modules.users import User
from indico.util.console import cformat
from indico.util.string import is_valid_mail
from indico.util.struct.iterables import committing_iterator

from indico_zodbimport import Importer, convert_to_unicode


def _sanitize_email(email):
    if '<' not in email:
        return email
    m = re.search(r'<([^>]+)>', email)
    return email if m is None else m.group(1)


class UserImporter(Importer):
    def has_data(self):
        return bool(User.find().count())

    def migrate(self):
        self.users_by_primary_email = {}
        self.users_by_secondary_email = {}
        self.migrate_users()
        self.fix_sequences('users', {'users'})

    def migrate_users(self):
        print cformat('%{white!}migrating users')

        for avatar in committing_iterator(self._iter_avatars(), 5000):
            if getattr(avatar, '_mergeTo', None):
                print cformat('%{red!}!!!%{reset} '
                              '%{yellow!}Skipping {} - merged into {}').format(avatar.id, avatar._mergeTo.id)
                continue
            elif avatar.status == 'Not confirmed':
                print cformat('%{yellow!}!!!%{reset} '
                              '%{yellow!}Skipping {} - not activated').format(avatar.id)
                continue
            elif not avatar.name.strip() and not avatar.surName.strip():
                links = {(obj, role): list(objs)
                         for obj, x in avatar.linkedTo.iteritems()
                         for role, objs in x.iteritems()
                         if objs}
                if not avatar.identities and not links:
                    print cformat('%{yellow!}!!!%{reset} '
                                  '%{yellow!}Skipping {} - no names and no identities/links').format(avatar.id)
                    continue

            user = self._user_from_avatar(avatar)
            print cformat('%{green}+++%{reset} '
                          '%{white!}{:6d}%{reset} %{cyan}{} {}%{reset} [%{blue!}{}%{reset}] '
                          '{{%{cyan!}{}%{reset}}}').format(user.id, user.first_name, user.last_name, user.email,
                                                           ', '.join(user.secondary_emails))
            self._fix_collisions(user)
            db.session.add(user)
            db.session.flush()
            for merged_avatar in getattr(avatar, '_mergeFrom', ()):
                merged = self._user_from_avatar(merged_avatar, is_deleted=True, merged_into_id=user.id)
                print cformat('%{blue!}***%{reset} '
                              '%{white!}{:6d}%{reset} %{cyan}{} {}%{reset} [%{blue!}{}%{reset}] '
                              '{{%{cyan!}{}%{reset}}}').format(merged.id, merged.first_name, merged.last_name,
                                                               merged.email, ', '.join(merged.secondary_emails))
                self._fix_collisions(merged)
                db.session.add(merged)
                db.session.flush()

    def _user_from_avatar(self, avatar, **kwargs):
        email = _sanitize_email(convert_to_unicode(avatar.email).lower().strip())
        secondary_emails = [_sanitize_email(convert_to_unicode(x).lower().strip()) for x in avatar.secondaryEmails]
        secondary_emails = [x for x in secondary_emails if x and is_valid_mail(x, False) and x != email]
        # we handle deletion later. otherwise it might be set before secondary_emails which would
        # result in those emails not being marked as deleted
        is_deleted = kwargs.pop('is_deleted', False)
        user = User(id=int(avatar.id),
                    email=email,
                    first_name=convert_to_unicode(avatar.name).strip() or 'UNKNOWN',
                    last_name=convert_to_unicode(avatar.surName).strip() or 'UNKNOWN',
                    phone=convert_to_unicode(avatar.telephone[0]).strip(),
                    affiliation=convert_to_unicode(avatar.organisation[0]).strip(),
                    address=convert_to_unicode(avatar.address[0]).strip(),
                    secondary_emails=secondary_emails,
                    is_blocked=avatar.status == 'disabled',
                    **kwargs)
        if is_deleted or not is_valid_mail(user.email):
            user.is_deleted = True
        return user

    def _fix_collisions(self, user):
        is_deleted = user.is_deleted
        # Mark both users as deleted if there's a primary email collision
        coll = self.users_by_primary_email.get(user.email)
        if coll and not is_deleted:
            for u in (user, coll):
                print cformat('%{magenta!}---%{reset} '
                              '%{yellow!}Deleting {} - primary email collision%{reset} '
                              '[%{blue!}{}%{reset}]').format(user.id, user.email)
                u.is_deleted = True
                db.session.flush()
        # if the user was already deleted we don't care about primary email collisions
        if not is_deleted:
            self.users_by_primary_email[user.email] = user

        # Remove primary email from another user's secondary email list
        coll = self.users_by_secondary_email.get(user.email)
        if coll and user.merged_into_id != coll.id:
            print cformat('%{magenta!}---%{reset} '
                          '%{yellow!}1 Removing colliding secondary email (P/S) from {}%{reset} '
                          '[%{blue!}{}%{reset}]').format(coll, user.email)
            coll.secondary_emails.remove(user.email)
            del self.users_by_secondary_email[user.email]
            db.session.flush()

        # Remove email from both users if there's a collision
        for email in list(user.secondary_emails):
            # colliding with primary email
            coll = self.users_by_primary_email.get(email)
            if coll:
                print cformat('%{magenta!}---%{reset} '
                              '%{yellow!}Removing colliding secondary email (S/P) from {}%{reset} '
                              '[%{blue!}{}%{reset}]').format(user, email)
                user.secondary_emails.remove(email)
                db.session.flush()
            # colliding with a secondary email
            coll = self.users_by_secondary_email.get(email)
            if coll:
                print cformat('%{magenta!}---%{reset} '
                              '%{yellow!}Removing colliding secondary email (S/S) from {}%{reset} '
                              '[%{blue!}{}%{reset}]').format(user, email)
                user.secondary_emails.remove(email)
                db.session.flush()
                self.users_by_secondary_email[email] = coll
            # if the user was already deleted we don't care about secondary email collisions
            if not is_deleted and email in user.secondary_emails:
                self.users_by_secondary_email[email] = user

    def _iter_avatars(self):
        return self.zodb_root['avatars'].itervalues()
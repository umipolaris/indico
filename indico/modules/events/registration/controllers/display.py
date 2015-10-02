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

from flask import request, session, redirect, flash
from werkzeug.exceptions import Forbidden

from indico.core.db import db
from indico.modules.auth.util import redirect_to_login
from indico.modules.events.registration.controllers import RegistrationFormMixin
from indico.modules.events.registration.models.forms import RegistrationForm
from indico.modules.events.registration.models.registrations import Registration
from indico.modules.events.registration.util import (get_event_section_data, make_registration_form)
from indico.modules.events.registration.views import (WPDisplayRegistrationFormConference,
                                                      WPDisplayRegistrationFormMeeting,
                                                      WPDisplayRegistrationFormLecture)
from indico.modules.payment import event_settings
from indico.util.i18n import _
from indico.web.flask.util import url_for
from MaKaC.webinterface.rh.conferenceDisplay import RHConferenceBaseDisplay


def _can_redirect_to_single_regform(regforms):
    user = session.user
    return len(regforms) == 1 and regforms[0].can_submit(user) and not regforms[0].get_user_registration(user)


class RHRegistrationFormDisplayBase(RHConferenceBaseDisplay):
    CSRF_ENABLED = True

    def _checkParams(self, params):
        RHConferenceBaseDisplay._checkParams(self, params)
        self.event = self._conf

    @property
    def view_class(self):
        mapping = {
            'conference': WPDisplayRegistrationFormConference,
            'meeting': WPDisplayRegistrationFormMeeting,
            'simple_event': WPDisplayRegistrationFormLecture
        }
        return mapping[self.event.getType()]


class RHRegistrationFormBase(RHRegistrationFormDisplayBase, RegistrationFormMixin):
    def _checkParams(self, params):
        RHRegistrationFormDisplayBase._checkParams(self, params)
        RegistrationFormMixin._checkParams(self)


class RHRegistrationFormList(RHRegistrationFormDisplayBase):
    """List of all registration forms in the event"""

    def _process(self):
        regforms = RegistrationForm.find_all(RegistrationForm.is_visible, event_id=int(self.event.id))
        if _can_redirect_to_single_regform(regforms):
            return redirect(url_for('.display_regform_summary', regforms[0]))
        return self.view_class.render_template('display/regform_list.html', self.event,
                                               event=self.event, regforms=regforms)


class RHRegistrationFormSummary(RHRegistrationFormBase):
    """Displays user summary for a registration form"""

    def _process(self):
        return self.view_class.render_template('display/regform_summary.html', self.event,
                                               event=self.event, regform=self.regform,
                                               registration=self.regform.get_user_registration(session.user),
                                               payment_enabled=event_settings.get(self.event, 'enabled'))


class RHRegistrationFormSubmit(RHRegistrationFormBase):
    """Submit a registration form"""

    normalize_url_spec = {
        'locators': {
            lambda self: self.regform
        }
    }

    def _checkProtection(self):
        RHRegistrationFormBase._checkProtection(self)
        if self.regform.require_user and not session.user:
            raise Forbidden(response=redirect_to_login(reason=_('You are trying to register with a form '
                                                                'that requires you to be logged in')))

    def _checkParams(self, params):
        RHRegistrationFormBase._checkParams(self, params)
        if not self.regform.is_active:
            flash(_('This registration form is not active'), 'error')
            return redirect(url_for('.display_regform_list', self.event))
        elif self.regform.get_user_registration(session.user):
            flash(_('You have already registered with this form'), 'error')
            return redirect(url_for('.display_regform_list', self.event))
        elif self.regform.limit_reached:
            flash(_('The maximum number of registrations has been reached'), 'error')
            return redirect(url_for('.display_regform_list', self.event))

    def _process(self):
        form = make_registration_form(self.regform)()
        if form.validate_on_submit():
            self._save_registration(form.data)
            return redirect(url_for('.display_regform_list', self.event))
        return self.view_class.render_template('display/regform_display.html', self.event, event=self.event,
                                               sections=get_event_section_data(self.regform), regform=self.regform,
                                               currency=event_settings.get(self.event, 'currency'))

    def _save_registration(self, data):
        registration = Registration(user=session.user, registration_form=self.regform)
        db.session.add(registration)
        for form_item in self.regform.active_fields:
            if form_item.parent.is_manager_only:
                value = form_item.wtf_field.default_value
            else:
                value = data.get('field_{0}-{1}'.format(form_item.parent_id, form_item.id))
            form_item.wtf_field.save_data(registration, value)
        db.session.flush()

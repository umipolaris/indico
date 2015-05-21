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

from flask import session

from indico.core.celery import celery
from indico.core.db import db
from indico.core.notifications import make_email, email_sender
from indico.modules.events.static import logger
from indico.modules.events.static.models.static import StaticSiteState
from indico.util.contextManager import ContextManager
from indico.util.fossilize import clearCache
from indico.util.i18n import _
from indico.web.flask.util import url_for

from MaKaC.accessControl import AccessWrapper
from MaKaC.common.offlineWebsiteCreator import OfflineEvent
from MaKaC.webinterface.rh.conferenceBase import RHCustomizable


@celery.task
def build_static_site(static_site):
    static_site.state = StaticSiteState.running
    db.session.commit()
    clearCache()
    try:
        logger.info('Building static site: {}'.format(static_site))
        session.lang = static_site.user.settings.get('lang')
        rh = RHCustomizable()
        rh._aw = AccessWrapper()
        rh._conf = rh._target = static_site.event

        ContextManager.set('currentRH', rh)
        ContextManager.set('offlineMode', True)

        # Get event type
        wf = rh.getWebFactory()
        event_type = wf.getId() if wf else 'conference'

        zip_archive = OfflineEvent(rh, rh._conf, event_type).create()

        static_site.path = zip_archive.getFilePath()
        static_site.state = StaticSiteState.success
        db.session.commit()

        logger.info('Building static site successful: {}'.format(static_site))
        ContextManager.set('offlineMode', False)
        ContextManager.set('currentRH', None)
        notify_static_site_success(static_site)
    except Exception:
        logger.exception('Building static site failed: {}'.format(static_site))
        static_site.state = StaticSiteState.failed
        db.session.commit()
        raise
    finally:
        ContextManager.set('offlineMode', False)
        ContextManager.set('currentRH', None)


@email_sender
def notify_static_site_success(static_site):
    to_list = [static_site.user.email]
    subject = _("Static version of an event ready for download")
    body = _("Dear {user.full_name},\n\n"
             "The static version for the event {event_title} is ready to be downloaded.\n\n"
             "Download link: {link}\n\n"
             'Best Regards,\n--\nIndico').format(user=static_site.user,
                                                 event_title=static_site.event.getTitle(),
                                                 link=url_for('static_site.download', static_site, _external=True))
    return make_email(to_list, subject=subject, body=body, html=False)
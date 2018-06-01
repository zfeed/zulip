# -*- coding: utf-8 -*-
from django.conf import settings
from django.utils.timezone import now as timezone_now

from zerver.lib.import_realm import (
    do_import_realm,
)
from zerver.lib.test_classes import (
    ZulipTestCase,
)
from zerver.tests.test_import_export import (
    rm_tree,
)
from zerver.lib.test_helpers import (
    get_test_image_file,
)
from zerver.models import (
    Realm,
    get_realm,
)
from zerver.lib.gitter_import import (
    do_convert_data,
)

import ujson
import json
import logging
import shutil
import os
import mock
from typing import Any, AnyStr, Dict, List, Optional, Set, Tuple

class GitterImporter(ZulipTestCase):
    logger = logging.getLogger()
    # set logger to a higher level to suppress 'logger.INFO' outputs
    logger.setLevel(logging.WARNING)

    def _make_output_dir(self) -> str:
        output_dir = 'var/test-gitter-import'
        rm_tree(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    @mock.patch('zerver.lib.gitter_import.process_avatars', return_value=[])
    def test_gitter_import_to_existing_database(self, mock_process_avatars: mock.Mock) -> None:
        output_dir = self._make_output_dir()
        gitter_file = os.path.join(os.path.dirname(__file__), 'fixtures/gitter_data.json')
        do_convert_data(gitter_file, output_dir)

        def read_file(output_file: str) -> Any:
            full_path = os.path.join(output_dir, output_file)
            with open(full_path) as f:
                return ujson.load(f)

        def get_set(data: List[Dict[str, Any]], field: str) -> Set[str]:
            values = set(r[field] for r in data)
            return values

        self.assertEqual(os.path.exists(os.path.join(output_dir, 'avatars')), True)
        self.assertEqual(os.path.exists(os.path.join(output_dir, 'emoji')), True)
        self.assertEqual(os.path.exists(os.path.join(output_dir, 'attachment.json')), True)

        realm = read_file('realm.json')

        # test realm
        self.assertEqual('Organization imported from Gitter!',
                         realm['zerver_realm'][0]['description'])

        # test users
        exported_user_ids = get_set(realm['zerver_userprofile'], 'id')
        exported_user_full_name = get_set(realm['zerver_userprofile'], 'full_name')
        self.assertIn('User Full Name', exported_user_full_name)
        exported_user_email = get_set(realm['zerver_userprofile'], 'email')
        self.assertIn('username2@users.noreply.github.com', exported_user_email)

        # test stream
        self.assertEqual(len(realm['zerver_stream']), 1)
        self.assertEqual(realm['zerver_stream'][0]['name'], 'from gitter')
        self.assertEqual(realm['zerver_stream'][0]['deactivated'], False)
        self.assertEqual(realm['zerver_stream'][0]['realm'], realm['zerver_realm'][0]['id'])

        self.assertEqual(realm['zerver_defaultstream'][0]['stream'], realm['zerver_stream'][0]['id'])

        # test recipient
        exported_recipient_id = get_set(realm['zerver_recipient'], 'id')
        exported_recipient_type = get_set(realm['zerver_recipient'], 'type')
        self.assertEqual(set([1, 2]), exported_recipient_type)

        # test subscription
        exported_subscription_userprofile = get_set(realm['zerver_subscription'], 'user_profile')
        self.assertEqual(set([0, 1]), exported_subscription_userprofile)
        exported_subscription_recipient = get_set(realm['zerver_subscription'], 'recipient')
        self.assertEqual(len(exported_subscription_recipient), 3)
        self.assertIn(realm['zerver_subscription'][1]['recipient'], exported_recipient_id)

        messages = read_file('messages-000001.json')

        # test messages
        exported_messages_id = get_set(messages['zerver_message'], 'id')
        self.assertIn(messages['zerver_message'][0]['sender'], exported_user_ids)
        self.assertIn(messages['zerver_message'][1]['recipient'], exported_recipient_id)
        self.assertIn(messages['zerver_message'][0]['content'], 'test message')

        # test usermessages
        exported_usermessage_userprofile = get_set(messages['zerver_usermessage'], 'user_profile')
        self.assertEqual(exported_user_ids, exported_usermessage_userprofile)
        exported_usermessage_message = get_set(messages['zerver_usermessage'], 'message')
        self.assertEqual(exported_usermessage_message, exported_messages_id)

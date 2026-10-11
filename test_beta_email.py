import unittest
from unittest.mock import Mock

from beta_email import BetaMailer, GRAPH_SEND_URL


class OutlookDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.mailer = BetaMailer(self.store)
        self.mailer._access_token = Mock(return_value=('test-token', {'sender_email': 'align@example.com'}))
        self.requests = []

        def graph_request(method, url, token, payload=None, timeout=20):
            self.requests.append((method, url, token, payload))
            return 202, None, {}

        self.mailer._graph_request = graph_request

    def test_invitation_code_is_sent_from_connected_graph_mailbox(self):
        result = self.mailer.send_invite(
            'tester@example.com', 'Tester', 'ALIGN-1234-5678-9ABC',
            'https://getalign.co.uk/invite', '2030-01-01T00:00:00Z',
        )

        self.assertEqual(result['status'], 'sent')
        method, url, token, payload = self.requests[0]
        self.assertEqual((method, url, token), ('POST', GRAPH_SEND_URL, 'test-token'))
        self.assertEqual(payload['message']['toRecipients'][0]['emailAddress']['address'], 'tester@example.com')
        self.assertIn('ALIGN-1234-5678-9ABC', payload['message']['body']['content'])
        self.assertTrue(payload['saveToSentItems'])

    def test_password_reset_and_account_update_use_graph_mail(self):
        self.mailer.send_reset('person@example.com', 'RESET-AAAA-BBBB-CCCC', 'https://getalign.co.uk')
        self.mailer.send_account_update(
            'person@example.com', 'Align — Your password was changed',
            'The password for your Align account was changed.',
        )

        self.assertEqual(len(self.requests), 2)
        reset = self.requests[0][3]['message']
        notice = self.requests[1][3]['message']
        self.assertIn('RESET-AAAA-BBBB-CCCC', reset['body']['content'])
        self.assertEqual(notice['subject'], 'Align — Your password was changed')
        self.assertIn('contact Align support', notice['body']['content'])


if __name__ == '__main__':
    unittest.main()

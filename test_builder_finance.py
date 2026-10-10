import json
import subprocess
import unittest
from datetime import date
from pathlib import Path

import builder_finance as finance
import owner_builder as builder
from test_owner_builder import BuilderTests


def template():
    script = "global.window={};require('./static/builder-finance.js');console.log(JSON.stringify(window.AlignFinance.template('finance')));"
    return json.loads(subprocess.check_output(['node', '-e', script], cwd=Path(__file__).parent))


class FinanceCalculations(unittest.TestCase):
    def values(self, **changes):
        return dict(category='Repayment', name='Example', label='Personal', total_due=100,
                    next_payment='2026-01-31', due_date='2026-03-31', frequency='Monthly',
                    payment_mode='Calculate from dates', **changes)

    def test_month_end_and_final_rounding(self):
        values = finance.calculate(self.values())
        self.assertEqual((values['payment_count'], values['payment_amount'], values['final_payment']), (3, 33.34, 33.32))
        self.assertEqual(finance.payment_count(date(2028, 1, 31), date(2028, 3, 30), 'Monthly'), 2)

    def test_manual_override_and_no_deadline(self):
        values = self.values()
        values.update(payment_mode='Enter payment amount', no_due_date=True, due_date='', manual_payment=20)
        self.assertEqual(finance.calculate(values)['payment_amount'], 20)
        values['payment_mode'] = 'Calculate from dates'
        with self.assertRaisesRegex(ValueError, 'Without a final'): finance.calculate(values)

    def test_bill_normalization_and_wishlist_exclusion(self):
        values = dict(category='Monthly payment / bill', amount=12, frequency='Weekly', next_payment='2026-10-01')
        self.assertEqual(finance.calculate(values)['monthly_amount'], 52)
        values.update(category='One-off / wishlist', amount=999)
        self.assertEqual(finance.calculate(values)['monthly_amount'], 0)

    def test_invalid_dates_amounts_and_tiny_balance(self):
        values = self.values()
        values['due_date'] = '2026-01-01'
        with self.assertRaises(ValueError): finance.calculate(values)
        for amount in ('nan', 'inf', -1, 0):
            with self.assertRaises(ValueError): finance.money(amount, 'test')
        values = self.values()
        values['total_due'] = '.01'
        self.assertEqual(finance.calculate(values)['final_payment'], .01)

    def test_conditions_clear_hidden_inputs_and_custom_labels(self):
        fields = builder.fields_validate(template()['fields'])
        result = builder.values_validate(fields, {'category':'One-off / wishlist','name':'Bike','label':'New label','amount':150,'total_due':'not a number'})
        self.assertEqual(result['label'], 'New label')
        self.assertEqual(result['total_due'], '')
        self.assertEqual(result['next_payment'], '')
        with self.assertRaises(builder.BuilderError): builder.values_validate(fields, {'category':'Monthly payment / bill','name':'Bill','label':'Home','amount':10})


class FinanceAPI(BuilderTests):
    def test_finance_preview_save_private_edit_roundtrip(self):
        current, doc = self.fixture()
        doc['layouts'].append(template())
        status, config = self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)
        self.assertEqual(status, 200, config)
        self.assertTrue(config['published']['layouts'][-1]['review_before_save'])
        token = self.users[0][1]
        path = '/api/builder/records/finance'
        values = FinanceCalculations().values()
        status, preview = self.request('POST',path+'/preview',{'values':values},token)
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview['values']['payment_amount'], 33.34)
        self.assertEqual(self.request('GET',path,token=token)[1]['records'], [])
        status, saved = self.request('POST',path,{'id':'repayment','values':values},token)
        self.assertEqual(status, 200, saved)
        records = self.request('GET',path,token=token)[1]['records']
        self.assertEqual(records[0]['values']['payment_amount'], 33.34)
        self.assertEqual(self.request('GET',path,token=self.users[1][1])[1]['records'], [])
        values.update(payment_mode='Enter payment amount',manual_payment=10,no_due_date=True,due_date='')
        self.assertEqual(self.request('PUT',path+'/repayment',{'revision':1,'values':values},token)[0],200)
        self.assertEqual(self.request('GET',path,token=token)[1]['records'][0]['values']['payment_amount'],10)


if __name__ == '__main__': unittest.main()

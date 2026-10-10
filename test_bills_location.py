import unittest
from unittest.mock import patch
from datetime import datetime
import bill_calculations as bills
import owner_builder as builder
import personal_planner as personal


class BillsLocationTests(unittest.TestCase):
    def fields(self, expression='[Amount] - [Paid]'):
        return [dict(id='amount',label='Amount',type='number',required=True,help='',options=[]),
                dict(id='paid',label='Paid',type='number',required=True,help='',options=[]),
                dict(id='balance',label='Balance',type='formula',formula=expression,required=False,help='',options=[])]

    def test_money_and_untrusted_submitted_result(self):
        fields=builder.fields_validate(self.fields())
        result=builder.values_validate(fields,dict(amount='0.30',paid='0.10',balance=999))
        self.assertEqual(result['balance'],0.20)
        fields[2]['formula']='[Amount] / 3'
        self.assertEqual(builder.values_validate(fields,dict(amount=10,paid=0))['balance'],3.33)

    def test_validation_and_missing_inputs(self):
        for expression in ('__import__("os")','[Missing] + 1','[Balance] + 1','2 ** 100','[Amount].real'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):
                builder.fields_validate(self.fields(expression))
        with self.assertRaisesRegex(ValueError,'zero'):
            bills.calculate(self.fields('[Amount] / [Paid]'),dict(amount=5,paid=0))
        with self.assertRaisesRegex(ValueError,'Fill in'):
            bills.calculate(self.fields(),dict(amount=5))

    def test_phone_weather_skips_geocoding(self):
        response={'current':{'temperature_2m':20},'hourly':{'time':['2030-01-01T12:00'],'temperature_2m':[20]},'daily':{'temperature_2m_min':[10]}}
        with patch.object(personal,'fetch_json',return_value=response) as fetch:
            result=personal.weather(None,dict(latitude=53.123456,longitude=-3.123456))
            self.assertEqual(result['place'],'Near your current location')
            self.assertEqual(fetch.call_count,1)
            self.assertIn('latitude=53.12',fetch.call_args.args[0])
            self.assertIn('hourly', result)
        for coords in (dict(latitude=91,longitude=0),dict(latitude='nan',longitude=0),dict(latitude=2)):
            with self.assertRaises(ValueError):personal.weather(None,coords)

    def test_phone_route_origin_and_summer_walking(self):
        class Connection:
            def execute(self,*args):return self
            def fetchone(self):return ['']
        route={'duration':'1800s','legs':[{'steps':[
            {'travelMode':'WALK','staticDuration':'300s'},
            {'transitDetails':{'stopDetails':{'departureTime':'2030-07-02T10:20:00Z','arrivalTime':'2030-07-02T10:40:00Z'}}},
            {'travelMode':'WALK','staticDuration':'300s'}]}]}
        with patch.object(personal,'preferences',return_value=personal.DEFAULTS),patch.dict(personal.os.environ,{'ALIGN_GOOGLE_ROUTES_KEY':'test'}),patch.object(personal,'fetch_json',return_value={'routes':[route]}) as fetch:
            result=personal.google_journey(Connection(),dict(latitude=53,longitude=-3,destination='Test',mode='bus',arrival='2030-07-02T12:00'))
            self.assertEqual(fetch.call_args.args[1]['origin'],{'location':{'latLng':{'latitude':53.,'longitude':-3.}}})
            self.assertEqual(result['leave_at'],'2030-07-02T11:10+01:00')
            self.assertEqual(result['arrival_at'],'2030-07-02T11:45+01:00')
            self.assertIn('current location',result['notes'])

if __name__=='__main__':unittest.main()

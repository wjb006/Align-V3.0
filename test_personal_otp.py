import unittest
from unittest.mock import patch
import personal_planner as personal
import personal_otp as otp
from transport_providers import ProviderUnavailable

class Connection:
    def execute(self,*args):return self
    def fetchone(self):return ['Home CH41 6AZ']

class PersonalOTPTests(unittest.TestCase):
    def body(self):return dict(mode='transit',arrival='2030-07-02T12:00',destination='Event L1 1JD')
    def routes(self):
        return [dict(legs=[
            dict(mode='walk',start='2030-07-02T10:00:00+00:00',end='2030-07-02T10:05:00+00:00',service='',**{'from':'Origin','to':'Stop'}),
            dict(mode='bus',start='2030-07-02T10:10:00+00:00',end='2030-07-02T10:30:00+00:00',service='42',**{'from':'Stop','to':'Station'}),
            dict(mode='walk',start='2030-07-02T10:30:00+00:00',end='2030-07-02T10:35:00+00:00',service='',**{'from':'Station','to':'Destination'})])]
    def test_default_home_walking_wait_and_no_google(self):
        with patch.object(personal,'preferences',return_value=personal.DEFAULTS),patch.object(otp,'resolve_place',return_value=((53.,-3.),'postcode centre')) as resolve,patch.object(otp.OTPProvider,'plan',return_value=self.routes()) as provider,patch.dict(personal.os.environ,{'ALIGN_JOURNEY_PROVIDER':'otp'}):
            result=personal.journey(Connection(),self.body())
            self.assertEqual(resolve.call_args_list[0].args[0],'Home CH41 6AZ')
            self.assertEqual(provider.call_args.args[3],['walk','bus','rail'])
            self.assertEqual(result['leave_at'],'2030-07-02T10:55+01:00')
            self.assertEqual(result['minutes'],35)
            self.assertEqual([s['mode'] for s in result['steps']],['walk','wait','bus','walk'])
            self.assertIn('scheduled times',result['notes'])
    def test_phone_does_not_resolve_home(self):
        with patch.object(otp,'resolve_place',return_value=((53.,-3.),'postcode centre')) as resolve,patch.object(otp.OTPProvider,'plan',return_value=self.routes()) as provider:
            otp.plan(Connection(),{**self.body(),'latitude':54,'longitude':-2},personal.DEFAULTS)
            self.assertEqual(resolve.call_count,1)
            self.assertEqual(provider.call_args.args[0],(54.,-2.))
    def test_unavailable_and_late_and_mode(self):
        with patch.object(otp,'resolve_place',return_value=((53.,-3.),'postcode centre')),patch.object(otp.OTPProvider,'plan',side_effect=ProviderUnavailable()):
            with self.assertRaisesRegex(ValueError,'unavailable'):otp.plan(Connection(),self.body(),personal.DEFAULTS)
        with patch.object(otp,'resolve_place',return_value=((53.,-3.),'postcode centre')),patch.object(otp.OTPProvider,'plan',return_value=self.routes()):
            with self.assertRaisesRegex(ValueError,'No scheduled'):otp.plan(Connection(),{**self.body(),'arrival':'2030-07-02T11:20'},personal.DEFAULTS)
        with self.assertRaisesRegex(ValueError,'Apple Maps'):otp.plan(Connection(),{**self.body(),'mode':'drive'},personal.DEFAULTS)
    def test_only_postcode_shared(self):
        with patch.object(otp,'request_json',return_value={'result':{'latitude':53,'longitude':-3}}) as request:
            otp.resolve_place('123 Private Road CH41 6AZ')
            self.assertNotIn('Private',request.call_args.args[0])
            self.assertIn('CH41%206AZ',request.call_args.args[0])
    def test_invalid_phone_location(self):
        with self.assertRaisesRegex(ValueError,'valid phone'):
            otp.plan(Connection(),{**self.body(),'latitude':float('nan'),'longitude':0},personal.DEFAULTS)

if __name__=='__main__':unittest.main()

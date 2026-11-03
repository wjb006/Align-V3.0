"""Server-side HERE transit adapter. Enable only after account/quota review."""
import os
from datetime import datetime
from urllib.parse import urlencode

from transport_providers import request_json, ProviderUnavailable

RAIL = ('highSpeedTrain', 'intercityTrain', 'interRegionalTrain',
        'regionalTrain', 'cityTrain', 'subway', 'lightRail', 'monorail')
BUS = ('bus', 'privateBus', 'busRapid')


class HERETransitProvider:
    def plan(self, origin, destination, target, modes, depart_after=False):
        if os.environ.get('ALIGN_HERE_TRANSIT_ENABLED') != '1':
            raise ValueError('HERE bus/train routing is awaiting account and free-plan verification.')
        key = os.environ.get('ALIGN_HERE_ROUTING_KEY')
        if not key:
            raise ValueError('The owner needs to configure the HERE routing key on the hosted server.')
        allowed = [m for group, names in [('bus', BUS), ('rail', RAIL)]
                   if group in modes for m in names]
        params = dict(origin=','.join(map(str, origin)),
                      destination=','.join(map(str, destination)),
                      arrivalTime=target.isoformat(), modes=','.join(allowed),
                      alternatives=3, lang='en-GB', apiKey=key)
        if depart_after: params['departureTime'] = params.pop('arrivalTime')
        from here_quota import reserve
        reserve()
        response = request_json('https://transit.router.hereapi.com/v8/routes?' + urlencode(params))
        journeys = []
        try:
            for route in response.get('routes', []):
                legs = []
                attributions = []
                for section in route.get('sections', []):
                    transport = section.get('transport') or {}
                    raw_mode = transport.get('mode')
                    mode = ('walk' if raw_mode == 'pedestrian' else
                            'bus' if raw_mode in BUS else 'rail' if raw_mode in RAIL else None)
                    if mode not in modes:
                        legs = []
                        break
                    departure, arrival = section['departure'], section['arrival']
                    if departure.get('status') in ('cancelled', 'replaced'):
                        legs = []
                        break
                    for attribution in section.get('attributions', []):
                        text = str(attribution.get('text') or '')
                        href = str(attribution.get('href') or '')
                        if href.startswith(('https://', 'http://')):
                            text += ' ' + href
                        if text and text not in attributions:
                            attributions.append(text)
                    start, end = (datetime.fromisoformat(x['time'].replace('Z', '+00:00'))
                                  for x in (departure, arrival))
                    if not start.tzinfo or not end.tzinfo or end < start:
                        legs = []
                        break
                    if legs and start < datetime.fromisoformat(legs[-1]['end']):
                        legs = []
                        break
                    legs.append(dict(mode=mode, start=start.isoformat(), end=end.isoformat(),
                                     service=transport.get('name') or '',
                                     service_number=transport.get('shortName') or transport.get('name') or '',
                                     platform=((departure.get('place') or {}).get('platform') or '') if mode == 'rail' else '',
                                     live=False,
                                     **{'from': (departure.get('place') or {}).get('name') or '',
                                        'to': (arrival.get('place') or {}).get('name') or ''}))
                # HERE can return an extra walking-only alternative.
                if legs and any(leg['mode'] != 'walk' for leg in legs):
                    journeys.append({'legs': legs, 'attributions': attributions, 'provider': 'HERE'})
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ProviderUnavailable('HERE returned an unreadable journey') from None
        return journeys

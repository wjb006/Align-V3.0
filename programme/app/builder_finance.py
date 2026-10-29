"""Opt-in finance layout calculations. No external services or executable formulas."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_UP

CATEGORIES = ('Monthly payment / bill', 'Repayment', 'One-off / wishlist')
FREQUENCIES = {'Weekly': 52, 'Fortnightly': 26, 'Monthly': 12, 'Quarterly': 4, 'Yearly': 1}
FIELD_TYPES = {'category': 'select', 'name': 'text', 'label': 'select', 'amount': 'number',
               'next_payment': 'date', 'frequency': 'select', 'total_due': 'number',
               'no_due_date': 'checkbox', 'due_date': 'date', 'payment_mode': 'select',
               'manual_payment': 'number'}


def validate_fields(fields):
    lookup = {f['id']: f for f in fields}
    if any(lookup.get(key, {}).get('type') != kind for key, kind in FIELD_TYPES.items()):
        raise ValueError('Keep the Finance template fields and their types; labels and help text can be edited.')
    for key, options in [('category', CATEGORIES), ('frequency', FREQUENCIES),
                         ('payment_mode', ('Calculate from dates', 'Enter payment amount'))]:
        if set(lookup[key]['options']) != set(options) or lookup[key].get('allow_custom'):
            raise ValueError('Keep the standard Finance category, frequency and payment calculation choices.')


def money(value, label):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000000000'):
            raise ValueError()
        amount = amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if amount == 0: raise ValueError()
        return amount
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a positive amount for ' + label + '.') from None


def payment_count(start, end, frequency):
    if end < start: raise ValueError('The final due date must be on or after the next payment date.')
    if frequency in ('Weekly', 'Fortnightly'):
        return (end - start).days // (7 if frequency == 'Weekly' else 14) + 1
    months = {'Monthly': 1, 'Quarterly': 3, 'Yearly': 12}[frequency]
    count = 0
    for index in range(12001):
        offset = start.month - 1 + index * months
        year, month = start.year + offset // 12, offset % 12 + 1
        if year > 9999: break
        current = date(year, month, min(start.day, monthrange(year, month)[1]))
        if current > end: break
        count += 1
    else: raise ValueError('Choose a shorter repayment period.')
    return count


def calculate(values):
    result = dict(values)
    category = values.get('category')
    if category not in CATEGORIES: raise ValueError('Choose a Finance category.')
    result.update(payment_amount=0, monthly_amount=0, payment_count='', final_payment='')
    if category == CATEGORIES[2]:
        result['payment_amount'] = float(money(values.get('amount'), 'amount'))
        return result
    frequency = values.get('frequency')
    if frequency not in FREQUENCIES: raise ValueError('Choose a payment frequency.')
    try: start = date.fromisoformat(values.get('next_payment', ''))
    except (ValueError, TypeError): raise ValueError('Enter the next payment date.') from None
    if category == CATEGORIES[0]:
        amount = money(values.get('amount'), 'amount')
    else:
        total = money(values.get('total_due'), 'total amount due')
        end = None
        if not values.get('no_due_date'):
            try: end = date.fromisoformat(values.get('due_date', ''))
            except (ValueError, TypeError): raise ValueError('Enter the final due date or select no final due date.') from None
            if end < start: raise ValueError('The final due date must be on or after the next payment date.')
        mode = values.get('payment_mode')
        if mode == 'Calculate from dates':
            if end is None: raise ValueError('Without a final due date, choose Enter payment amount.')
            count = payment_count(start, end, frequency)
            amount = (total / count).quantize(Decimal('.01'), rounding=ROUND_UP)
            # Avoid negative final payments for very small balances spread over many dates.
            count = min(count, int((total / amount).to_integral_value(rounding=ROUND_UP)))
            result['payment_count'] = count
            result['final_payment'] = float(total - amount * (count - 1))
        elif mode == 'Enter payment amount':
            amount = money(values.get('manual_payment'), 'payment amount')
            if amount > total: raise ValueError('The payment amount cannot exceed the total amount due.')
        else: raise ValueError('Choose how to set the repayment amount.')
    result['payment_amount'] = float(amount)
    result['monthly_amount'] = float((amount * FREQUENCIES[frequency] / 12).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    return result
def workflow():
    """Finance workflow/tree used by the Builder."""
    return {
        'version': 1,
        'start_node': 'finance_type',

        'nodes': [
            {
                'id': 'finance_type',
                'type': 'choice',
                'field_id': 'category',
            },
            {
                'id': 'finance_name',
                'type': 'field',
                'field_id': 'name',
            },
            {
                'id': 'finance_label',
                'type': 'field',
                'field_id': 'label',
            },
            {
                'id': 'finance_amount',
                'type': 'field',
                'field_id': 'amount',
            },

            {
                'id': 'repayment_total_due',
                'type': 'field',
                'field_id': 'total_due',
            },
            {
                'id': 'repayment_no_due_date',
                'type': 'choice',
                'field_id': 'no_due_date',
            },
            {
                'id': 'repayment_due_date',
                'type': 'field',
                'field_id': 'due_date',
            },

            {
                'id': 'finance_next_payment',
                'type': 'field',
                'field_id': 'next_payment',
            },
            {
                'id': 'finance_frequency',
                'type': 'field',
                'field_id': 'frequency',
            },

            {
                'id': 'repayment_payment_mode',
                'type': 'choice',
                'field_id': 'payment_mode',
            },
            {
                'id': 'repayment_manual_payment',
                'type': 'field',
                'field_id': 'manual_payment',
            },

            {
                'id': 'finance_calculation',
                'type': 'calculation',
                'operation': 'finance_calculate',
                'inputs': [
                    'amount',
                    'total_due',
                    'no_due_date',
                    'due_date',
                    'next_payment',
                    'frequency',
                    'payment_mode',
                    'manual_payment',
                ],
                'outputs': [
                    'payment_amount',
                    'monthly_amount',
                    'payment_count',
                    'final_payment',
                ],
            },

            {
                'id': 'finance_summary',
                'type': 'summary',
                'title': 'Summary / Confirm',
                'visible_fields': 'current_branch',
            },

            {
                'id': 'finance_save',
                'type': 'save',
                'record_type': 'finance',
            },

            {
                'id': 'finance_home',
                'type': 'destination',
                'screen': 'finance_summary',
            },
        ],

        'edges': [
            {
                'from': 'finance_type',
                'to': 'finance_name',
            },
            {
                'from': 'finance_name',
                'to': 'finance_label',
            },

            # Monthly Payment / Bill
            {
                'from': 'finance_label',
                'to': 'finance_amount',
                'when': {
                    'field': 'category',
                    'equals': 'Monthly payment / bill',
                },
            },
            {
                'from': 'finance_amount',
                'to': 'finance_next_payment',
                'when': {
                    'field': 'category',
                    'equals': 'Monthly payment / bill',
                },
            },

            # Repayment
            {
                'from': 'finance_label',
                'to': 'repayment_total_due',
                'when': {
                    'field': 'category',
                    'equals': 'Repayment',
                },
            },
            {
                'from': 'repayment_total_due',
                'to': 'repayment_no_due_date',
            },
            {
                'from': 'repayment_no_due_date',
                'to': 'repayment_due_date',
                'when': {
                    'field': 'no_due_date',
                    'equals': False,
                },
            },
            {
                'from': 'repayment_no_due_date',
                'to': 'finance_next_payment',
                'when': {
                    'field': 'no_due_date',
                    'equals': True,
                },
            },
            {
                'from': 'repayment_due_date',
                'to': 'finance_next_payment',
            },

            # Shared recurring payment route
            {
                'from': 'finance_next_payment',
                'to': 'finance_frequency',
            },
            {
                'from': 'finance_frequency',
                'to': 'finance_calculation',
                'when': {
                    'field': 'category',
                    'equals': 'Monthly payment / bill',
                },
            },

            # Repayment calculation choice
            {
                'from': 'finance_frequency',
                'to': 'repayment_payment_mode',
                'when': {
                    'field': 'category',
                    'equals': 'Repayment',
                },
            },
            {
                'from': 'repayment_payment_mode',
                'to': 'finance_calculation',
                'when': {
                    'field': 'payment_mode',
                    'equals': 'Calculate from dates',
                },
            },
            {
                'from': 'repayment_payment_mode',
                'to': 'repayment_manual_payment',
                'when': {
                    'field': 'payment_mode',
                    'equals': 'Enter payment amount',
                },
            },
            {
                'from': 'repayment_manual_payment',
                'to': 'finance_calculation',
            },

            # One-off / Wishlist
            {
                'from': 'finance_label',
                'to': 'finance_amount',
                'when': {
                    'field': 'category',
                    'equals': 'One-off / wishlist',
                },
            },
            {
                'from': 'finance_amount',
                'to': 'finance_summary',
                'when': {
                    'field': 'category',
                    'equals': 'One-off / wishlist',
                },
            },

            # Finish recurring branches
            {
                'from': 'finance_calculation',
                'to': 'finance_summary',
            },

            {
                'from': 'finance_summary',
                'to': 'finance_save',
                'action': 'confirm',
            },
            {
                'from': 'finance_save',
                'to': 'finance_home',
                'on': 'success',
            },
        ],
    }
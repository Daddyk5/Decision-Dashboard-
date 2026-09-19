"""Rice grades, unit conversions and quoting for the B2B order page.

PLACEHOLDER PRICING: the per-tonne prices and lead-time bands below are illustrative defaults, not
Rice Enterprise's real price list. Replace them here (and only here); the order form, the live price
preview in the browser and the stored order total all read from this module.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')

# key -> (label shown to the customer and stored on the order, price in $ per metric ton)
RICE_GRADES = {
    'jasmine-premium-5': ('Jasmine Premium 5%', Decimal('950.00')),
    'basmati-white-1121': ('Basmati White 1121', Decimal('1180.00')),
    'long-grain-white-25': ('Long Grain White 25%', Decimal('460.00')),
    'broken-rice': ('Broken Rice', Decimal('350.00')),
}

# unit key -> (label, kilograms per unit)
UNITS = {
    'tons': ('Metric tons', Decimal('1000')),
    'bags': ('50 kg bags', Decimal('50')),
}

MAX_ORDER_TONS = Decimal('10000')

# (up to this many metric tons, business days to fulfil), checked in order.
SLA_BANDS = ((Decimal('20'), 3), (Decimal('100'), 5), (MAX_ORDER_TONS, 7))


@dataclass(frozen=True)
class Quote:
    kilograms: Decimal
    metric_tons: Decimal
    unit_price: Decimal
    total: Decimal
    sla_days: int


def grade_choices():
    return [(key, label) for key, (label, _price) in RICE_GRADES.items()]


def unit_choices():
    return [(key, label) for key, (label, _kg) in UNITS.items()]


def sla_days(metric_tons):
    for limit, days in SLA_BANDS:
        if metric_tons <= limit:
            return days
    return SLA_BANDS[-1][1]


def quote(grade_key, unit_key, quantity):
    """Price an order. `quantity` is a Decimal in the chosen unit."""
    _label, unit_price = RICE_GRADES[grade_key]
    kilograms = (quantity * UNITS[unit_key][1]).quantize(CENT, rounding=ROUND_HALF_UP)
    metric_tons = kilograms / Decimal('1000')
    return Quote(
        kilograms=kilograms,
        metric_tons=metric_tons.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP),
        unit_price=unit_price,
        total=(metric_tons * unit_price).quantize(CENT, rounding=ROUND_HALF_UP),
        sla_days=sla_days(metric_tons),
    )


def browser_catalog():
    """The same numbers as above, shaped for the live preview script (strings, so no float drift)."""
    return {
        'grades': {key: {'label': label, 'price': str(price)} for key, (label, price) in RICE_GRADES.items()},
        'units': {key: {'label': label, 'kg': str(kg)} for key, (label, kg) in UNITS.items()},
        'slaBands': [[str(limit), days] for limit, days in SLA_BANDS],
    }

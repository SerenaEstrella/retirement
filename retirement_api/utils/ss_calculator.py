"""
experimenting with SS quick-calculator page as trial api for demo pages

users must be at least 22 to use the form
users past their full retirement age will get only their current benefit amount

Well need to ask user for DOB and current annual earnings
we'll return estimated benefits at 62, 67, and 70 based the value of the dollar today

inputs needed:
    Date of birth: 8/14/1956
    Current earnings: 50000

optional inputs:
    Last year with earnings # could be useful for users who are retired or unemployed
    Last earnings # ditto
    Retirement month/year: 8/2026) # feed won't return 3 retire options if we provide this
    Benefit in year-2015 dollars) # SS can take today's dollars (1) or future, inflated dollars (0)
"""
import re
import requests
import json
import datetime
import math

from bs4 import BeautifulSoup as bs
from .ss_utilities import get_retirement_age, get_current_age, past_fra_test

base_url = "http://www.ssa.gov"
quick_url = "%s/OACT/quickcalc/" % base_url# where users go, but not needed for our request
result_url = "%s/cgi-bin/benefit6.cgi" % base_url
chart_ages = range(62,71)
benefits = {}
for age in chart_ages:
    benefits["age %s" % age] = 0

comment = re.compile(r"<!--[\s\S]*?-->")# regex for parsing indexing data; not used yet

def clean_comment(comment):
    return comment.replace('<!--', '').replace('-->', '').strip()

## unused, but needs a test
# def parse_comments(req, results):
#     """
#     this pulls indexing details out of the source comments 
#     on SSA's quick-calculator results page 
#     and adds it to the results payload;  
#     we are not yet using this data
#     """
#     raw_comments = comment.findall(req.text)
#     comments = [clean_comment(com) for com in raw_comments if clean_comment(com) and not clean_comment(com).startswith('Indexed') and not clean_comment(com).startswith('Nominal')]
#     headings = [term.strip() for term in comments[0].split()]
#     headings.pop(headings.index('max'))
#     headings[headings.index('Tax')] = 'Tax_max'
#     detail_rows = []
#     details = []
#     for row in comments[1:]:
#         if num_test(row.split()[0]):
#             detail_rows.append([cell.strip() for cell in row.split()])
#         else:
#             details.append(row)
#     for row in detail_rows:
#         results['earnings_data'].append({tup[0]: tup[1] for tup in zip(headings, row)})
#     results['benefit_details']['family_max'] = details.pop(-1)
#     results['benefit_details']['indexing']={}
#     INDEXING = results['benefit_details']['indexing']
#     sets = len(details) / 3
#     i1, i2 = (-3, 0)
#     for i in range(sets):
#         i1 += 3
#         i2 += 3
#         INDEXING.update(parse_details(details[i1:i2]))
#     return results

def num_test(value=''):
    try:
        num = int(value)
    except:
        try:
            num = int(float(value))
        except:
            return False
        else: return True
    else:
        return True

# unused for now
def parse_details(rows):
    datad = {}
    if len(rows) == 3:
        titlerow = rows[0].split(':')
        datad[titlerow[0].strip().upper()] = {'Bend points': titlerow[1].strip()}
        outer = datad[titlerow[0].strip().upper()]
        outer['AIME']  = rows[1]
        outer['COLA'] = rows[2]
    return datad

def interpolate_benefits(benefits, fra_tuple, current_age):
    """
    estimates missing benefit values, because SSA provides no more than 3
    need to handle these cases:
        FRA could be 66, or 67 (folks with FRA of 65 older than their FRA)
        visitor could be between the ages of 55 and 65, which requires special handliing
            their FRA is 66, which changes where we need to fill in the chart
        visitor could be too young to use the tool (< 22)
        visitor's age could be past the FRA, in which case only current benefit is returned
            if current age is 67, 68, 69 or 70, we can show that beneift in the chart
            if current age is > 70, chart zeroes out and we deliver benefit in text
    """
    fra = fra_tuple[0]# could be 66 or 67
    if not fra:
        return benefits
    # fill out the missing years, working backward and forward from the FRA
    if fra == 67:
        base = benefits['age 67']
        benefits['age 63'] = int(round(base - base*( 3*12*(0.00555555) ) - base*( 1*12*0.004166666 ) ))
        benefits['age 64'] = int(round(base - base*( 3*12*(0.00555555) )))
        benefits['age 65'] = int(round(base - base*( 2*12*(0.00555555) )))
        benefits['age 66'] = int(round(base - base*( 1*12*(0.00555555) )))
        benefits['age 68'] = int(round(base + (base * 0.08)))
        benefits['age 69'] = int(round(base + (2 * (base * 0.08))))
    elif fra == 66:
        base = benefits['age 66']
        benefits['age 67'] = int(round(base + (base * 0.08)))
        benefits['age 68'] = int(round(base + (2 * (base* 0.08))))
        benefits['age 69'] = int(round(base + (3 * (base* 0.08))))
        if current_age == 65:# FRA is 66; need to fill in 65
            base = benefits['age 66']
            benefits['age 65'] = int(round(base - base*( 12*(0.00555555) )))
        elif current_age == 64:#FRA is 66; need to fill in 64 and 65
            base = benefits['age 66']
            benefits['age 64'] = int(round(base - base*( 2*12*(0.00555555) )))
            benefits['age 65'] = int(round(base - base*( 12*(0.00555555) )))
        elif current_age in range(55, 64):# 55 to 63: FRA is 66
            base = benefits['age 66']
            benefits['age 63'] = int(round(base - base*( 3*12*(0.00555555) )))
            benefits['age 64'] = int(round(base - base*( 2*12*(0.00555555) )))
            benefits['age 65'] = int(round(base - base*( 12*(0.00555555) )))
    return benefits

#sample params
params = {
    'dobmon': 8,
    'dobday': 14,
    'yob': 1970,
    'earnings': 70000,
    'lastYearEarn': '',# possible use for unemployed or already retired
    'lastEarn': '',# possible use for unemployed or already retired
    'retiremonth': '',# leve blank to get triple calculation -- 62, 67 and 70
    'retireyear': '',# leve blank to get triple calculation -- 62, 67 and 70
    'dollars': 1,# benefits to be calculated in current-year dollars
    'prgf': 2
}
def get_retire_data(params):
    starter = datetime.datetime.now()
    dobstring = "%s-%s-%s" % (params['yob'], params['dobmon'], params['dobday'])
    collector = {}
    results = {'data': {
                    'early retirement age': '', 
                    'full retirement age': '', 
                    'benefits': benefits,
                    'params': params,
                    'disability': '',
                    'survivor benefits': {
                                    'child': '',
                                    'spouse caring for child': '',
                                    'spouse at full retirement age': '',
                                    'family maximum': ''
                                    }
                    },
                'current_age': 0,
                'error': ''
              }
    BENS = results['data']['benefits']
    past_fra = past_fra_test(dobstring)
    if past_fra == False:
        pass
    elif past_fra == True:
        results['error'] = 'Visitor is past full retirement age'
    elif 'invalid' in past_fra:
        results['error'] = past_fra
        return json.dumps(results)
    elif 'too young' in past_fra:
        results['error'] = past_fra
        return json.dumps(results)
    current_age = get_current_age(dobstring)
    results['current_age'] = current_age
    req = requests.post(result_url, data=params)
    # if req.reason != 'OK':
    #     results['error'] = "request to Social Security failed: %s %s" % (req.reason, req.status_code)
    #     print results['error']
    #     return json.dumps(results)
    # else:
    fra_tuple = get_retirement_age(params['yob'])
    soup = bs(req.text)
    if past_fra == True:
        ret_amount = soup.find('span', {'id': 'ret_amount'}).text.split('.')[0].replace(',', '')
        if current_age == 67:
            BENS['age 68'] = int(ret_amount)
            BENS['age 69'] = round(BENS['age 68'] + BENS['age 68'] * 0.08)
            BENS['age 70'] = round(BENS['age 68'] + 2*BENS['age 68'] * 0.08)
        elif current_age == 68:
            BENS['age 69'] = int(ret_amount)
            BENS['age 70'] = round(BENS['age 69'] + BENS['age 69'] * 0.08)
        elif current_age == 69:
            BENS['age 70'] = int(ret_amount)
        elif current_age == 70:
            BENS['age 70'] = int(ret_amount)
        pass
    else:
        tables = soup.findAll('table', {'bordercolor': '#6699ff'})
        results_table, disability_table, survivors_table = (None, None, None)
        for each in tables:
            if each.find('th') and 'Retirement age' in each.find('th').text:
                results_table = each
            elif each.find('th') and 'Disability' in each.find('th').text:
                disability_table = each
            elif each.find('th') and "Survivors" in each.find('th').text:
                survivors_table = each
        if results_table:
            result_rows = results_table.findAll('tr')
            for row in result_rows:
                cells = row.findAll('td')
                if cells:
                    collector[cells[0].text] = cells[1].text
            """
            collector:
            70 in 2047: "$2,719.00",
            67 in 2044: "$2,180.00",
            62 and 1 month in 2039: "$1,515.00"

            results['data']:
                'early retirement age': '', 
                'full retirement age': '', 
                'benefits': {
                    'age 62': 0, 

            """
            for key in collector:
                bits = key.split(' in ')
                benefit_age_raw = bits[0]
                benefit_age_year = bits[0].split()[0]
                # benefit_in_year = bits[1]# not using
                benefit_raw = collector[key]
                benefit = int(benefit_raw.split('.')[0].replace(',', '').replace('$', ''))
                if benefit_age_year == str(fra_tuple[0]):
                    results['data']['full retirement age'] = benefit_age_raw
                    BENS['age %s' % benefit_age_year] = benefit
                if benefit_age_year == '62':
                    results['data']['early retirement age'] = benefit_age_raw
                    BENS['age %s' % benefit_age_year] = benefit
                if benefit_age_year == '70':
                    BENS['age %s' % benefit_age_year] = benefit
            additions = interpolate_benefits(BENS, fra_tuple, current_age)
            for key in BENS:
                if additions[key] and not BENS[key]:
                    BENS[key] = additions[key]
        if disability_table:
            results['data']['disability'] = disability_table.findAll('td')[1].text.split('.')[0]
        # SURVIVORS KEYS 
        # 'Your child'
        # 'Family maximum'
        # 'Your spouse at normal retirement age'
        # 'Your spouse caring for your child'
        #
        # RESULTS['DATA']['SURVIVOR BENEFITS'] KEYS
        # 'spouse at full retirement age'
        # 'family maximum'
        # 'spouse caring for child'
        # 'child'
        if survivors_table:
            SURV = results['data']['survivor benefits']
            survivors = {}
            survivor_rows = survivors_table.findAll('tr')
            for row in survivor_rows:
                cells = row.findAll('td')
                if cells:
                    survivors[cells[0].text] = cells[1].text.split('.')[0]
            if 'Your child' in survivors:
                SURV['child'] = survivors['Your child']
            if 'Family maximum' in survivors:
                SURV['family maximum'] = survivors['Family maximum']
            if 'Your spouse at normal retirement age' in survivors:
                SURV['spouse at full retirement age'] = survivors['Your spouse at normal retirement age']
            if 'Your spouse caring for your child' in survivors:
                SURV['spouse caring for child'] = survivors['Your spouse caring for your child']
    print "script took %s to run" % (datetime.datetime.now() - starter)
    # # to dump json for testing:
    # with open('/tmp/ssa.json', 'w') as f:
    #     f.write(json.dumps(results))
    return json.dumps(results)


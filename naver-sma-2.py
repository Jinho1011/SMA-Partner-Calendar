# -*- coding:utf-8 -*-
from __future__ import print_function
import datetime
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import lzstring
import re
import requests
import rsa
import time
import json
import uuid
import unicodedata
from dateutil.parser import parse
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from pathlib import Path
from bs4 import BeautifulSoup
from pytz import timezone, utc


def get_partner_booking_api_url():
    today = datetime.now()
    dday = today + timedelta(days=30)
    start_date = today.strftime('%Y-%m-%d') + 'T00%3A00%3A00.000Z'
    end_date = dday.strftime('%Y-%m-%d') + 'T00%3A00%3A00.000Z'
    return 'https://partner.booking.naver.com/api/businesses/167437/bookings?bizItemTypes=STANDARD&bookingStatusCodes=&dateDropdownType=MONTH&dateFilter=USEDATE&endDateTime=' + end_date + '&maxDays=31&nPayChargedStatusCodes=&orderBy=&orderByStartDate=ASC&paymentStatusCodes=&searchValue=&searchValueCode=USER_NAME&startDateTime=' + start_date + '&page=0&size=50&noCache=1593413152922'


def encrypt(key_str, uid, upw):
    def naver_style_join(l):
        return ''.join([chr(len(s)) + s for s in l])

    sessionkey, keyname, e_str, n_str = key_str.split(',')
    e, n = int(e_str, 16), int(n_str, 16)

    message = naver_style_join([sessionkey, uid, upw]).encode()

    pubkey = rsa.PublicKey(e, n)
    encrypted = rsa.encrypt(message, pubkey)

    return keyname, encrypted.hex()


def encrypt_account(uid, upw):
    key_str = requests.get(
        'https://nid.naver.com/login/ext/keys.nhn').content.decode("utf-8")
    return encrypt(key_str, uid, upw)


def naver_session(nid, npw):
    encnm, encpw = encrypt_account(nid, npw)

    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.1,
        status_forcelist=[500, 502, 503, 504]
    )
    s.mount('https://', HTTPAdapter(max_retries=retries))
    request_headers = {
        'User-agent': 'Mozilla/5.0'
    }

    bvsd_uuid = uuid.uuid4()
    encData = '{"a":"%s-4","b":"1.3.4","d":[{"i":"id","b":{"a":["0,%s"]},"d":"%s","e":false,"f":false},{"i":"%s","e":true,"f":false}],"h":"1f","i":{"a":"Mozilla/5.0"}}' % (
        bvsd_uuid, nid, nid, npw)
    bvsd = '{"uuid":"%s","encData":"%s"}' % (
        bvsd_uuid, lzstring.LZString.compressToEncodedURIComponent(encData))

    resp = s.post('https://nid.naver.com/nidlogin.login', data={
        'svctype': '0',
        'enctp': '1',
        'encnm': encnm,
        'enc_url': 'http0X0.0000000000001P-10220.0000000.000000www.naver.com',
        'url': 'www.naver.com',
        'smart_level': '1',
        'encpw': encpw,
        'bvsd': bvsd
    }, headers=request_headers)

    finalize_url = re.search(
        r'location\.replace\("([^"]+)"\)', resp.content.decode("utf-8")).group(1)
    s.get(finalize_url)

    return s


def calendar(summary, start_date, end_date, refund):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None
    if os.path.exists('C:\\Users\\music\\Downloads\\Naver-Partner-Google-Calendar-master\\Naver-Partner-Google-Calendar-master\\token.pickle'):
        with open('C:\\Users\\music\\Downloads\\Naver-Partner-Google-Calendar-master\\Naver-Partner-Google-Calendar-master\\token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'C:\\Users\\music\\Downloads\\Naver-Partner-Google-Calendar-master\\Naver-Partner-Google-Calendar-master\\credentials.json', SCOPES)
            creds = flow.run_local_server(port=3030)
        # Save the credentials for the next run
        with open('C:\\Users\\music\\Downloads\\Naver-Partner-Google-Calendar-master\\Naver-Partner-Google-Calendar-master\\token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('calendar', 'v3', credentials=creds)

    today = datetime.date.today()
    from_ = datetime.datetime(today.year, today.month, today.day, 0, 0, 0,
                              tzinfo=datetime.timezone.utc).isoformat()
    events_result = service.events().list(calendarId='sma.orangefox@gmail.com', timeMin=from_,
                                          maxResults=100, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    for event in events:
        if summary == event["summary"] and str(start_date+"+09:00") == event['start']['dateTime']:
            if refund > 0:
                print("Refunded Customer")
                delete_event = service.events().delete(
                    calendarId='sma.orangefox@gmail.com', eventId=event["id"]).execute()
                return
            else:
                print("Overlapped Customer")
                return

    event = {
        'summary': summary,
        'start': {
            'dateTime': start_date,
            'timeZone': 'Asia/Seoul',
        },
        'end': {
            'dateTime': end_date,
            'timeZone': 'Asia/Seoul',
        }
    }

    event = service.events().insert(
        calendarId='sma.orangefox@gmail.com', body=event, sendUpdates=None, sendNotifications=None).execute()
    print("Customer Added")


if __name__ == "__main__":
    SESSION = naver_session('jinho9940', 'jinho1221!')
    NAVER_BOOKING_LIST_API_URL = get_partner_booking_api_url()

    req = SESSION.get(NAVER_BOOKING_LIST_API_URL)
    booking_list = json.loads(req.text)

    for customer in booking_list:
        is_booking_opt_exist = customer["bookingOptionJson"]
        booking_refund = customer["refundPrice"]

        # Set calendar_summary as customer name
        calendar_summary = customer["bizItemName"].split(
            ' ')[0] + " " + customer["name"]

        # If customers are more than 1, Add the number of customers
        if (customer["bookingCount"] > 1):
            calendar_summary = calendar_summary + str(customer["bookingCount"])

        # Set calendar start & end date
        start_date_str = (parse(
            customer["snapshotJson"]["startDateTime"]) + timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S')
        end_date_str = (parse(
            customer["snapshotJson"]["endDateTime"]) + timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S')

        # If Booking Option Exist, Add Booking Option to Summary
        if is_booking_opt_exist:
            booking_opt_name = customer["bookingOptionJson"][0]["name"]
            booking_opt_cnt = customer["bookingOptionJson"][0]["bookingCount"]
            bookgin_opt = " (" + booking_opt_name + " " + \
                str(booking_opt_cnt) + ")"
            calendar_summary += bookgin_opt

        print("##", calendar_summary, "##")
        calendar(calendar_summary, start_date_str,
                 end_date_str, booking_refund)

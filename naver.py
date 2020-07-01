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

SCOPES = ['https://www.googleapis.com/auth/calendar']
creds = None
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=3030)
    # Save the credentials for the next run
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)
service = build('calendar', 'v3', credentials=creds)


def get_url():
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


def calendar(summary, starD, endD):
    event = {
        'summary': summary,
        'start': {
            'dateTime': starD,
            'timeZone': 'Asia/Seoul',
        },
        'end': {
            'dateTime': endD,
            'timeZone': 'Asia/Seoul',
        }
    }

    now = datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(calendarId='gino9940@gmail.com', timeMin=now,
                                          maxResults=100, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    isOverlapped = False

    for e in events:
        if summary == e['summary'] and str(starD+"+09:00") == e['start']['dateTime']:
            isOverlapped = True

    if (not isOverlapped):
        event = service.events().insert(
            calendarId='gino9940@gmail.com', body=event).execute()


if __name__ == "__main__":
    naver_login_info = {
        "id": '',
        "pwd": ''
    }
    session = naver_session(naver_login_info.id, naver_login_info.pwd)

    NAVER_BOOKING_LIST_API_URL = get_url()
    req = session.get(NAVER_BOOKING_LIST_API_URL)
    book_json = json.loads(req.text)

    for customer in book_json:
        summary = customer["bizItemName"].split(
            ' ')[0] + " " + customer["name"]
        if (customer["bookingCount"] > 1):
            summary = summary + str(customer["bookingCount"])
        start_date_str = customer["snapshotJson"]["startDateTime"]
        start_date_obj = (parse(start_date_str) +
                          timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S')
        end_date_str = customer["snapshotJson"]["endDateTime"]
        end_date_obj = (parse(end_date_str) + timedelta(hours=9)
                        ).strftime('%Y-%m-%dT%H:%M:%S')
        calendar(summary, start_date_obj, end_date_obj)

# -*- coding: utf-8 -*-
"""BL2026 - Brushfire to Google Sheets sync"""

import pandas as pd
import numpy as np
import gspread
import os
import re
import json
import requests
from google.oauth2 import service_account
from oauth2client.service_account import ServiceAccountCredentials

# Set option to display all columns
pd.set_option('display.max_columns', None)

# Load service account from environment variable (set as GitHub Actions secret)
service_account_info = json.loads(os.environ['BL_SERVICE_ACCOUNT'])

def remove_whitespace(df):
    return df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scopes=scope)
client = gspread.authorize(creds)

spreadsheet = client.open_by_url(
    "https://docs.google.com/spreadsheets/d/1GJGob7hlQeJqYv-CwhGoDYPJ-F4mZ-RXvHxpOnftQDU/edit"
)

# Fetch data from Brushfire API
url = "https://api.brushfire.com/events/626836/data?type=Attendee&includeCancelled=false"
application_key = "cy4fn6rf8wn6hq2d"

headers = {
    "Authorization": application_key,
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Api-Version": "2026-03-01"
}

response = requests.get(url, headers=headers)
print("Response status code", response.status_code)

if response.status_code == 200:
    data = response.json()
    df = pd.DataFrame(data)
    print("DataFrame head:")
    print(df.head())
else:
    print("Failed to fetch data from API:", response.text)
    exit(1)

df.info()

df.columns = df.columns.str.replace("’", "'", regex=False)

df2 = df[[
    "Event Title", "Order Date",
    "Hey there! What's your name? (First)",
    "Hey there! What's your name? (Last)",
    "Hey there! What's your name? (Combined)",
    "What is your email address?",
    "What is your phone number?",
    "Do you live at least FOUR hours' drive away from the Greater Toronto Area?",
    "What Country do you live in?",
    "We'd like to know where you're joining us from",
    "Province",
    "What city do you live in?",
    "Name of your city",
    "You indicated that you live at least 4 hours' drive away from the GTA. You qualify as an Inner Circle member and you will get free a Conference Shirt. What is your shirt size?",
    "Are you between the ages of 17-35?",
    "What's your age range?",
    "THAT GRL is a BL segment for ladies 17-35. Will you be attending?",
    "Will you be coming with any children ages 17 and under?",
    "What church do you attend? (Please type the full name)",
    "We'd like to know the name of your church",
    "How did you hear about Balance Living Conference?",
    "We'd really love to know how you heard about BL",
    "Finally, are you interested in volunteering at the conference?",
    "How many children are you coming with?  (Please note that child care will NOT be provided)",
    "Have you attended the Balance Living Women's Conference before?",
    "We're excited to have you! Are you planning on attending In Person or Online?"
]]

df2['unique_id'] = (
    df2["Hey there! What's your name? (Combined)"].astype(str) + "_" +
    df2["What is your email address?"].astype(str)
)

columns_to_check = [
    "Hey there! What's your name? (First)",
    "Hey there! What's your name? (Last)",
    "Hey there! What's your name? (Combined)"
]

df_cleaned = df2.dropna(subset=columns_to_check, how="all")

def remove_duplicate_customers(df):
    grouped = df.groupby("unique_id")
    cleaned_df = grouped.first().reset_index()
    return cleaned_df

cleaned_df = remove_duplicate_customers(df_cleaned)
duplicate_customers = df[df.duplicated(subset="Hey there! What's your name? (Combined)", keep=False)]

cleaned_df['Order Date'] = pd.to_datetime(cleaned_df['Order Date'])
cleaned_df['Order Date'] = cleaned_df['Order Date'].dt.tz_localize('UTC')
cleaned_df['Order Date'] = cleaned_df['Order Date'].dt.tz_convert('America/New_York')

cleaned_df['week'] = cleaned_df['Order Date'].dt.to_period('W').dt.start_time
cleaned_df["date"] = cleaned_df['Order Date'].dt.date
cleaned_df["How many children are you coming with?  (Please note that child care will NOT be provided)"] = pd.to_numeric(
    cleaned_df["How many children are you coming with?  (Please note that child care will NOT be provided)"],
    errors='coerce'
).fillna("")

cleaned_df["date"] = cleaned_df["date"].astype(str)
cleaned_df['Order Date'] = cleaned_df['Order Date'].astype(str)
cleaned_df['week'] = cleaned_df['week'].astype(str)

cleaned_df.rename(columns={
    "Hey there! What's your name? (First)": 'First_name',
    "Hey there! What's your name? (Last)": 'Last_name',
    "Hey there! What's your name? (Combined)": 'Combined_name',
    'What is your email address?': 'Email',
    'What is your phone number?': 'Phone Number',
    "Do you live at least FOUR hours' drive away from the Greater Toronto Area?": 'Inner Circle Eligible',
    'What Country do you live in?': 'Country',
    "You indicated that you live at least 4 hours' drive away from the GTA. You qualify as an Inner Circle member and you will get free a Conference Shirt. What is your shirt size": 'inner_circle_t_shirt_size',
    "We're excited to have you! Are you planning on attending In Person or Online?": "Online or In-Person"
}, inplace=True)

cleaned_df = cleaned_df[~cleaned_df["First_name"].str.contains(r'\bTest\b', case=False)]

# List 1: substring matches in "What city do you live in?"
cities_list1 = [
    "Toronto", "Vaughan", "Whitby", "Mississauga", "Brampton", "Richmond Hill", "Oakville",
    "Niagara Falls", "St. Catharines", "Barrie", "Cambridge", "Other", "Oshawa", "Milton",
    "Burlington", "Haldimand County", "Brantford", "Hamilton", "Woodstock", "Peterborough",
    "Markham", "London", "Kingston", "St. Thomas", "Belleville", "Owen Sound", "Welland",
    "Waterloo", "Kitchener", "Brant", "Ajax", "Orillia", "Pickering", "Guelph", "Thorold",
    "Stratford", "Thornhill"
]

# List 2: exact matches in "Name of your city"
cities_list2 = [
    "Bradford", "Orangeville", "Stoney creek", "Scarborough", "Mono", "Caledon", "Smithville",
    "Acton", "Baden", "Bolton", "Alliston", "Tillsonburg", "Shelburne", "Georgetown", "Listowel",
    "Paris", "North York", "Keswick", "Bowmanville", "Aurora"
]

pattern1 = re.compile(r"\b(" + "|".join(map(re.escape, cities_list1)) + r")\b", flags=re.IGNORECASE)

mask = (
    cleaned_df["Country"].fillna("").str.strip().str.lower().isin(["canada", ""]) &
    cleaned_df["Province"].fillna("").str.strip().str.lower().isin(["ontario", ""]) & (
        cleaned_df["What city do you live in?"].fillna("").str.contains(pattern1) |
        cleaned_df["Name of your city"].fillna("").str.lower().isin([c.lower() for c in cities_list2])
    )
)

cleaned_df["Inner Circle Eligible"] = np.where(mask, "No", "Yes")

# Read existing Google Sheet data
worksheet = spreadsheet.worksheet("cleaned_data")
existing_records = worksheet.get_all_records()
df_existing = pd.DataFrame(existing_records)

if not df_existing.empty:
    if 'unique_id' not in df_existing.columns:
        df_existing['unique_id'] = df_existing['combined_name'].astype(str) + "_" + df_existing['email'].astype(str)

# Identify and append only new rows
if not df_existing.empty:
    new_rows_mask = ~cleaned_df['unique_id'].isin(df_existing['unique_id'])
    df_new_rows = cleaned_df[new_rows_mask].copy()
else:
    df_new_rows = cleaned_df.copy()

print(f"Found {len(df_new_rows)} new rows to add.")

if not df_new_rows.empty:
    columns_to_upload = df_new_rows.columns.tolist()
    rows_to_append = df_new_rows[columns_to_upload].values.tolist()
    worksheet.append_rows(rows_to_append, value_input_option='RAW')
    print("New rows appended successfully!")
else:
    print("No new rows to add.")

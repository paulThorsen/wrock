# to automate email
import smtplib, ssl
import json
import requests
import re
import os
import pytz

from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from io import StringIO


def getCurrentDay():
    """
    Returns current day with Provo UTC offset
    """
    now_utc = datetime.now(pytz.timezone("US/Mountain"))
    return str(now_utc).split()[0] + "T7:00:00Z"


# Might redo this one day to make it more readable but this was more fun, I guess...
def getTop5VideoTweetsOfToday(tweets):
    """
    Create (tweet, mediaExp) tuples that are sorted (descending order) by view count - top 5 most viewed video tweets are returned as [(tweet, mediaExp)...]
    """
    if len(tweets) == 0:
        return []
    tweets = sorted(
        [
            (
                next(
                    (
                        tweet
                        for tweet in tweets
                        if "attachments" in tweet
                        and mediaExp["media_key"]
                        == tweet["attachments"]["media_keys"][0]
                    ),
                    None,
                ),
                mediaExp,
            )
            for mediaExp in media
            if mediaExp["type"] == "video"
        ],
        key=lambda tweet: tweet[1]["public_metrics"]["view_count"],
        reverse=True,
    )[:5]
    tweets = list(filter(lambda tweet: tweet[0]["text"][:2] != "RT", tweets))
    return tweets


def fetchTweetsFrom(handle, url, headers):
    resp = requests.get(
        url.format(handle, getCurrentDay()),
        headers=headers,
    )
    if resp.status_code != 200:
        # probably should add some better error handling
        print(resp.text)
        exit
    return json.loads(resp.text)


def sendEmails(port, sender_email, password, recipients, email_subject):
    # Create SMTP session for sending the mail
    # Create a secure SSL context
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as session:
        session.login(sender_email, password)
        #  Create new email for each recipient
        for recipient in recipients:
            # Create the email head (sender and subject)
            email = MIMEMultipart("alternative")
            email["From"] = sender_email
            email[
                "Subject"
            ] = f'{email_subject} {datetime.today().strftime("%B %d, %Y")}'
            # Add body to email
            email.attach(MIMEText(body, "plain"))
            email.attach(MIMEText(html_body, "html"))
            email["To"] = recipient
            session.sendmail(sender_email, recipient, email.as_string())
            print("Mail sent successfully to " + recipient)
        session.quit()


def parseResp(resp, tweets, media):
    if "errors" in resp.keys():
        print(resp["errors"][0]["message"])
        return
    else:
        meta = resp["meta"]
        if meta["result_count"] > 0:
            tweets = resp["data"]
            if "includes" in resp.keys() and "media" in resp["includes"].keys():
                media = resp["includes"]["media"]
                return (tweets, media)
    return ([], [])


# Load ENV vars
load_dotenv()

BEARER_TOKEN = os.environ.get("TWITTER_API_BEARER_TOKEN")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
RECIPIENTS = str(os.environ.get("RECIPIENTS")).split("...")
TWITTER_API_URI = "https://api.twitter.com/2/tweets/search/recent?query=from:{}&start_time={}&max_results=100&tweet.fields=public_metrics,created_at,attachments,author_id&expansions=attachments.media_keys&media.fields=preview_image_url,type,duration_ms,width,public_metrics"
HEADERS_DICT = {"Authorization": "Bearer " + BEARER_TOKEN}

HTML_BUTTON_START = '<div style="margin: 20px 0 ; color: #f5f8fc; width: 100%; text-align: center; height: 50px; border-radius: 4px; background-color: #3468ad; line-height: 50px; font-weight: 600;">'
HTML_BUTTON_END = "</div>"

MAX_WIDTH = "600px"

EMAIL_SUBJECT = "Daily Sports Brief"
PORT = 465  # For SSL

ACCOUNT_HANDLES = ["espn", "bleacherreport", "HofHighlights"]

top5 = []
tweets = []
media = []

for handle in ACCOUNT_HANDLES:
    resp = fetchTweetsFrom(handle, TWITTER_API_URI, HEADERS_DICT)
    tweetsArr, mediaArr = parseResp(resp, tweets, media)
    tweets += tweetsArr
    media += mediaArr

top5 = getTop5VideoTweetsOfToday(tweets)

body = "Today's Top 5 ESPN Video Tweets\n\n"
html_body = f"""
    <html>
        <body style="color: #333; max-width: {MAX_WIDTH};">
            <h1 style="line-height: 40px;">Today's Top 5 Sports Video Tweets</h1>
    """

if len(top5) == 0:
    html_body += "<p>No cool videos were posted today ¯\_(ツ)_/¯</p>"

# Add tweets to body text
for i, tweet in enumerate(top5):
    # Exctract link to tweet - should be last link in tweet text
    link = re.search("https://t.co/\S+$", tweet[0]["text"])

    text = "{}\n\n".format(
        tweet[0]["text"][
            # Remove link from body text
            : re.search("https://t.co/\S+$", tweet[0]["text"]).start()
        ]
        # Remove new lines in body text
        .replace("\n", " "),
    )
    body += text

    html_body += f"<h2>{i + 1}.</h2>"
    html_body += f"<p>{text}</p>"
    html_body += f"<img style=\"max-width: {MAX_WIDTH};\" src=\"{tweet[1]['preview_image_url']}\">"
    html_body += f'<a style="text-decoration: none;" href="{link.group()}">{HTML_BUTTON_START}Watch video &#8599;{HTML_BUTTON_END}</a>'
    html_body += "<hr />"

html_body += """        
        </body>
    </html>
    """

sendEmails(PORT, SENDER_EMAIL, EMAIL_PASSWORD, RECIPIENTS, EMAIL_SUBJECT)

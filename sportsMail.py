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
from types import SimpleNamespace

# Load ENV vars
load_dotenv()

BEARER_TOKEN = os.environ.get("TWITTER_API_BEARER_TOKEN")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
RECIPIENTS = str(os.environ.get("RECIPIENTS")).split("...")
TWEETS_API_URI = "https://api.twitter.com/2/tweets/search/recent?query=from:{}&start_time={}&max_results=100&tweet.fields=public_metrics,created_at,attachments,author_id&expansions=attachments.media_keys&media.fields=preview_image_url,type,duration_ms,width,public_metrics"
ACCOUNTS_API_URI = (
    "https://api.twitter.com/2/users/by/username/{}?user.fields=public_metrics"
)

HEADERS_DICT = {"Authorization": "Bearer {}".format(BEARER_TOKEN)}
HTML_BUTTON_START = '<div style="margin: 20px 0 ; color: #f5f8fc; width: 100%; text-align: center; height: 50px; border-radius: 4px; background-color: #3468ad; line-height: 50px; font-weight: 600;">'
HTML_BUTTON_END = "</div>"
MAX_WIDTH = "600px"
EMAIL_SUBJECT = "Daily Sports Brief"
PORT = 465  # For SSL
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

ACCOUNT_HANDLES = ["espn", "HoHighlights", "BleacherReport"]


class VideoTweet:
    """
    A Tweet that has an embedded video

    Attributes:
        tweet: the data from the tweet. Fields should include public_metrics, created_at, attachments, author_id, text, id
        media: the associated video media. Fields should include public_metrics, type, preview_image_url, duration_ms, media_key, width
    """

    def __init__(self, tweet, media):
        self.tweet = tweet
        self.media = media

    tweet = None
    media = None


def fetchAccountInfo(handle, url, headers):
    """
    Returns info a account from handle.

        Parameters:
            handle (str): twitter account
            url (str): Base Twitter API
            headers ({"Authorization": "Bearer " + BEARER_TOKEN}): Object with Authorization bearer token

        Returns:
            respObj (obj)

    """
    resp = requests.get(
        url.format(handle),
        headers=headers,
    )
    if resp.status_code != 200:
        # probably should add some better error handling
        print(resp.status_code, resp.text)
        raise Exception(resp.status_code, resp.text)
        exit
    # Convert response to object
    respObj = json.loads(resp.text, object_hook=lambda d: SimpleNamespace(**d))
    print(respObj)
    return respObj.data


def scoreVideoTweet(videoTweet, accountInfo):
    """
    Returns videoTweet score: number of view divided by how many seconds old the tweet is
    """
    # TODO rework this scoring alg
    seconds_old = (
        datetime.utcnow()
        - datetime.strptime(videoTweet.tweet.created_at, DATETIME_FORMAT)
    ).total_seconds()
    score = (
        videoTweet.media.public_metrics.view_count / (seconds_old / 2)
    ) / accountInfo.public_metrics.followers_count
    print(str(score) + videoTweet.tweet.text)
    return score


def getCurrentDay():
    """
    Returns current day with Provo UTC offset
    """
    now_utc = datetime.now(pytz.timezone("US/Mountain"))
    return str(now_utc).split()[0] + "T7:00:00Z"


# Might redo this one day to make it more readable but this was more fun, I guess...
def getTop5VideoTweetsOfToday(tweets, accountsInfo):
    """
    Returns top 5 most watched VideoTweets that are sorted (descending order) by view count
    """
    if len(tweets) == 0:
        return []
    # Create VideoTweets from data
    # Create VideoTweet if there is an associated media_key and is not a RT
    videoTweets = [
        VideoTweet(
            next(
                (
                    tweet
                    for tweet in tweets
                    if hasattr(tweet, "attachments")
                    and hasattr(tweet.attachments, "media_keys")
                    and mediaExp.media_key == tweet.attachments.media_keys[0]
                ),
                None,
            ),
            mediaExp,
        )
        for mediaExp in media
        if mediaExp.type == "video"
    ]
    # Remove RT and other tweets where None is returned from next method above
    videoTweets = filter(
        lambda videoTweet: videoTweet.tweet.text[:2] != "RT"
        and videoTweet.tweet != None,
        videoTweets,
    )
    videoTweets = sorted(
        videoTweets,
        key=lambda videoTweet: scoreVideoTweet(
            videoTweet,
            next(
                (
                    account
                    for account in accountsInfo
                    if account.id == videoTweet.tweet.author_id
                ),
                None,
            ),
        ),
        reverse=True,
    )[:5]
    return videoTweets


def fetchTweetsFrom(handle, url, headers):
    """
    Returns all tweets from given handle for current day.

        Parameters:
            handle (str): twitter account
            url (str): Base Twitter API
            headers ({"Authorization": "Bearer " + BEARER_TOKEN}): Object with Authorization bearer token

        Returns:
            respJson (dict): see /json.json for json structure of tweets

    """
    resp = requests.get(
        url.format(handle, getCurrentDay()),
        headers=headers,
    )
    if resp.status_code != 200:
        # probably should add some better error handling
        print(resp.status_code, resp.text)
        raise Exception(resp.status_code, resp.text)
        exit
    # Convert response to object
    respObj = json.loads(resp.text, object_hook=lambda d: SimpleNamespace(**d))
    return respObj


def sendEmails(port, sender_email, password, recipients, email_subject):
    """
    Send emails to all recipients
    """
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
    """
    Parses JSON respons and returns ([tweets], [media_keys]) tuple
    """
    if hasattr(resp, "errors"):
        print(resp.errors[0].message)
        return
    else:
        meta = resp.meta
        if meta.result_count > 0:
            tweets = resp.data
            if hasattr(resp, "includes") and hasattr(resp.includes, "media"):
                media = resp.includes.media
                return (tweets, media)
    return ([], [])


def createEmail(top5):
    """
    Create HTML email to be sent to recipients
    """
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
        link = re.search("https://t.co/\S+$", tweet.tweet.text)

        text = "{}\n\n".format(
            tweet.tweet.text[
                # Remove link from body text
                : re.search("https://t.co/\S+$", tweet.tweet.text).start()
            ]
            # Remove new lines in body text
            .replace("\n", " "),
        )
        body += text

        html_body += f"<h2>{i + 1}.</h2>"
        html_body += f"<p>{text}</p>"
        html_body += f'<img style="max-width: {MAX_WIDTH};" src="{tweet.media.preview_image_url}">'
        html_body += f'<a style="text-decoration: none;" href="{link.group()}">{HTML_BUTTON_START}Watch video &#8599;{HTML_BUTTON_END}</a>'
        html_body += "<hr />"

    html_body += """        
            </body>
        </html>
        """
    return (body, html_body)


top5 = []
tweets = []
media = []
accountsInfo = []

for handle in ACCOUNT_HANDLES:
    resp = fetchTweetsFrom(handle, TWEETS_API_URI, HEADERS_DICT)
    tweetsArr, mediaArr = parseResp(resp, tweets, media)
    tweets += tweetsArr
    media += mediaArr
    accountsInfo.append(fetchAccountInfo(handle, ACCOUNTS_API_URI, HEADERS_DICT))

top5 = getTop5VideoTweetsOfToday(tweets, accountsInfo)
body, html_body = createEmail(top5)

sendEmails(PORT, SENDER_EMAIL, EMAIL_PASSWORD, RECIPIENTS, EMAIL_SUBJECT)

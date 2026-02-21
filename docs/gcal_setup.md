# Google Calendar Setup

It is recommended to create a dedicated Google account for your reservation system.
This way you can name the account something descriptive like "My Building Amenities".
This name will appear to users as the sender on confirmaton and reminder emails.

Once you have done that and logged in to your account, go to the [Google Cloud
console](https://console.cloud.google.com/apis/credentials), create a Google Cloud project
for your app, set it in test mode, and create an OAuth client ID with application type
"Desktop App". Then download the credentials file and store it in your .gcal-credentials
folder (which is expected to be in your project root by default).

!!! note "Fun Fact"

-   Confirmation emails are actually just Google Calendar event invites, and
    therefore users can easily add them to their own calendar, or even whitelist the
    account to have them added automatically.
-   Reminder emails are just event updates. The app server updates the title
    of the event from "[Resource] Reservation" to "Reminder: [Resource] Reservation" at
    the appointed time.


# reserve-it!

[![Tests](https://github.com/joshhubert-dsp/reserve-it/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/joshhubert-dsp/reserve-it/actions/workflows/test.yml)

A dead-simple reservation system web app framework, built on Google Calendar and
Mkdocs-Material, implemented as a Mkdocs plugin. Designed with the goal of making
communal sharing and coordination effortless and ubiquitous.

`reserve-it` is a lightweight framework that enables rapidly building a web app for
shared community amenity/resource reservations. It provides a customizable validation
logic layer around creating events in a restricted but publicly viewable Google
calendar. As a Mkdocs plugin, it makes use of Mkdocs-Material for the frontend build,
and so you can easily customize site aesthetics with tools from the Mkdocs
ecosystem in `mkdocs.yml`.

App users don't need to make an account, the base configuration only requires an email
address. You can choose whether or not to implement a shared password or other
authentication in the web form, see below.

![form page](./form-page.png)

## Basic Setup

All it takes to build a resource reservation system website for your organization/community:

1.  Make a dedicated Google account for your organization, and a Google calendar for each
    reservable resource. If you're familiar with the concept of "Resources" from Google
    Workspace, we're using individual calendars as a bootleg version of that.

2.  Set up an installed app client secret for your Google Calendar account. Detailed
    instructions forthcoming!

3.  Install the reserve-it package in your python environment with `pip install git+https://github.com/joshhubert-dsp/reserve-it`. PyPi package coming soon!

4.  To see a non-functional example of the site frontend build template on `localhost:8000`,
    run `reserve-it serve-example`. Note that the embedded calendar view won't work
    since it's serving the page template directly (you'll see a bit of jinja syntax that the
    app uses to serve it), but you'll get a decent idea anyway.

5.  If you like what you see, run `reserve-it init` to copy the necessary structure
    directly from the package's `example` directory into your current working 
    directory. If you have a `.gitignore` file already in your directory, the
    recommended default ignores will be appended. You'll end up with following
    structure:

    ```
    .
    ├── .gitignore
    ├── app-config.yaml
    ├── docs
    │ └── readme.md
    ├── mkdocs.yml
    ├── resource-configs
    │ ├── 1-chargers.yaml
    │ └── 2-courts.yaml
    └── server_example.py
    ```

6.  Modify the global config file `app-config.yaml` to suit your needs. Example:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=src/reserve_it/example/app-config.yaml) -->

    <!-- MARKDOWN-AUTO-DOCS:END -->

7.  Add your resource reservation config yaml files under `resource-configs`, one for each set of resources, like this:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=src/reserve_it/example/resource-configs/2-courts.yaml) -->

    <!-- MARKDOWN-AUTO-DOCS:END -->

8.  Modify the included Mkdocs config file `mkdocs.yml` to suit your aesthetic needs.
    Also if you want additional static pages added to your site, you can add them as
    markdown files under `docs` in standard Mkdocs fashion.

9.  Build the static portion of the site with `mkdocs build`. It will build to the
    directory `site` by (Mkdocs) default.

10. Write a simple python script to define custom form input validation, and then build
    the dynamic web app from the Mkdocs build:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=src/reserve_it/example/server_example.py) -->

    <!-- MARKDOWN-AUTO-DOCS:END -->

11. Host the app somewhere accessible to your community, and disseminate any shared
    passwords/validation information through communication channels.

## Features

-   You have the rich aesthetic customization capabilities of the Mkdocs ecosystem and
    Mkdocs-Material theme at your fingertips.
-   Users don't need to make accounts or log in, an email address is the only required
    form of identification.
-   Users receive email confirmation for their reservation in the form of a Google
    calendar invite. A reservation is represented by a normal calendar event that the
    user is invited to, which they can conveniently add to their own calendar.
-   Additionally users can opt to receive a reminder email N minutes before their
    reservation.
-   One reservation can be held per email address at a time. A minimal sqlite database
    is stored on the server to enforce this. Users can cancel their reservations to
    reschedule.
-   Each independently reservable resource (ie. a single tennis court) is backed by its
    own Google calendar. When a user submits a reservation, each included calendar is
    checked, and the first calendar found to be available during the selected time is
    selected.
-   The page elements, time granularity and other configuration for each set of
    related resources (ie. a set of tennis courts) are ergonomically defined in a single
    yaml file (see the yaml example [7] above). Each yaml file maps to a single
    reservation webpage.
-   Each reservation webpage displays a form input, and optionally an embedded calendar
    view and an arbitrary descriptive image you provide.
-   Yaml files are stored in the directory passed to `resource_config_path`. When more
    than one yaml file is present, a home page is automatically generated for navigating
    between reservation webpages, and the filenames are used for the endpoint paths.
-   For resources that can be shared between multiple users at once (like say, a sauna),
    users can select that they are willing to share with others. If they are, subsequent
    users who are willing to share can reserve overlapping times, while users who are
    not willing to share are barred from these times like normal.
-   You may define custom form input fields and validation logic either globally or per
    reservation page via the yaml file. This data will be available for validation only,
    but not stored to the database.
-   Webpage light/dark mode toggle that respects user system settings by default.

## TODO

-   If requested, could add flexibility in persistent database storage and related validation.

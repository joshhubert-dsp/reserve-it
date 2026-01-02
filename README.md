# reserve-it!

[![Tests](https://github.com/joshhubert-dsp/reserve-it/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/joshhubert-dsp/reserve-it/actions/workflows/test.yml)

A dead-simple reservation system framework, built on Google Calendar and Pydantic.

`reserve-it` is a lightweight framework that enables rapidly building a web server for shared community amenity/resource reservations.
It provides a customizable validation logic layer around creating events in a restricted but publicly
viewable Google calendar. Users don't need to make an account, the base configuration
only requires an email address. You can choose whether or not to implement a shared
password or other authentication in the web form, see below.

![form page](form-page.png)

If you have multiple resources to reserve, it automatically makes the root endpoint a
home page for navigating between them:
![home page](home-page.png)

## Basic Setup

All it takes to build a resource reservation system website for your organization/community:

1.  Make a dedicated Google account for your organization, and a Google calendar for each
    reservable resource.

2.  Create an app config yaml file, like this:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=app-config-example.yaml, syntax=yaml) -->
    <!-- MARKDOWN-AUTO-DOCS:END -->

3.  Create a folder of resource reservation config yaml files, one for each set of resources, like this:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=resource-config-examples/2-courts.yaml, syntax=yaml) -->
    <!-- MARKDOWN-AUTO-DOCS:END -->

4.  Write a simple python script to define custom form inputs, validation, and resource
    paths, and build the app:
    <!-- MARKDOWN-AUTO-DOCS:START (CODE:src=server_example.py, syntax=python) -->
    <!-- MARKDOWN-AUTO-DOCS:END -->

5.  Host the app somewhere accessible to your community, and disseminate any shared
    passwords/validation information through communication channels.

## Features

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
    yaml file (see the yaml example [3] above). Each yaml file maps to a single
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

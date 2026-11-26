{{HEADER}}

Apps for the Supervisor, custom integrations and dashboard cards for HACS, from one pipeline. This page
is generated from the catalogs and always shows the versions they currently pin.

## Get started

| I want to… | Do this |
| --- | --- |
| Install an app | Add the [app catalog](https://github.com/seb5594/Home-Assistant-Apps) with the blue button above, or in **Settings → Apps → App store → ⋮ → Repositories**. Then pick the app in the store. |
| Install an integration | Open the project's repository below and use the *HACS* badge in its README, or add it in **HACS → ⋮ → Custom repositories** with category **Integration**. |
| Install a dashboard card or theme | Open the project's repository below and use the *HACS* badge in its README, or add it in **HACS → ⋮ → Custom repositories** with category **Dashboard** (HACS calls cards `plugin`). HACS adds the card's resource for you; if a card does not show up, check **Settings → Dashboards → ⋮ → Resources**. |
| Report a problem or ask something | Open an issue in the repository of the project concerned. |

## Apps

📦 Add the [app catalog](https://github.com/seb5594/Home-Assistant-Apps) once, then pick any of these in the app store.

{{APPS}}

Apps are built for the architectures listed and run in the Home Assistant Supervisor. Details,
options and documentation are in each app's repository.

## Integrations

🧩 Each integration installs on its own through HACS or the Marketplace, no catalog needed.

{{INTEGRATIONS}}

Integrations install through HACS and are configured under **Settings → Devices & services**.
Only public projects are listed.

## Dashboards

🎨 Lovelace cards and themes. Each one installs on its own through HACS or the Marketplace, category **Dashboard**.

{{DASHBOARDS}}

Cards are added to a dashboard in edit mode (**Add card**); themes are picked in your profile. Details and
options are in each project's repository.

## How this works

Each app or integration lives in its own repository and ships through one shared pipeline. The
[app catalog](https://github.com/seb5594/Home-Assistant-Apps) and the
[integration catalog](https://github.com/seb5594/Home-Assistant-Integrations) pin the latest
version of every public project; dashboards are read straight from their repositories until they get
a catalog of their own. This hub renders the overview every hour and whenever a catalog changes.

{{SUPPORT}}

{{LICENSE_NOTE}}

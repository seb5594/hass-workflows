import json
import os
import glob
import sys
import argparse
import urllib.request
import yaml

GITHUB_USER = "seb5594"

def fetch_stars(repo_name):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}"
    req = urllib.request.Request(url, headers={'User-Agent': 'HA-Dashboard-Engine'})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("stargazers_count", 0), data.get("open_issues_count", 0)
    except Exception:
        return 0, 0

def parse_apps():
    apps = []
    config_files = glob.glob("apps/*/config.yaml") + glob.glob("apps/*/*/config.yaml") + glob.glob("apps-store/apps/*/config.yaml")
    
    for conf in config_files:
        with open(conf, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        parts = conf.split('/')
        repo_dir = parts[1] if parts[0] == "apps" else parts[2] if len(parts) > 2 else parts[1]
        stars, issues = fetch_stars(repo_dir)
        
        apps.append({
            "name": data.get("name", repo_dir),
            "version": data.get("version", "1.0.0"),
            "arch": data.get("arch", ["amd64", "aarch64"]),
            "description": data.get("description", "No description provided."),
            "repo": repo_dir,
            "stars": stars,
            "issues": issues
        })
    return sorted(apps, key=lambda x: x["name"].lower())

def parse_integrations():
    integrations = []
    manifest_files = glob.glob("integrations/*/custom_components/*/manifest.json") + glob.glob("integrations-store/integrations/*/custom_components/*/manifest.json")
    
    for mf in manifest_files:
        with open(mf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        parts = mf.split('/')
        repo_dir = parts[1] if parts[0] == "integrations" else parts[2] if len(parts) > 2 else parts[1]
        stars, issues = fetch_stars(repo_dir)
        
        integrations.append({
            "name": data.get("name", repo_dir),
            "version": data.get("version", "1.0.0"),
            "domain": data.get("domain", ""),
            "iot_class": data.get("iot_class", "local_polling"),
            "description": f"Custom Component for Home Assistant ({data.get('domain', '')}).",
            "repo": repo_dir,
            "stars": stars,
            "issues": issues
        })
    return sorted(integrations, key=lambda x: x["name"].lower())

def build_apps_block(apps):
    if not apps:
        return "*No applications registered yet.*
"
    
    md = "[![Add Repository to Home Assistant](https://my.home-assistant.io/badges/repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_repo/?repository_url=https%3A%2F%2Fgithub.com%2F" + GITHUB_USER + "%2FHome-Assistant-Apps)

"
    md += "### 📋 Applications Index

"
    for idx, app in enumerate(apps, 1):
        anchor = f"app-{app['name'].lower().replace(' ', '-')}"
        md += f"{idx}. [{app['name']}](#{anchor}) — *v{app['version']}*
"
    
    md += "
### 📦 Available Applications

"
    for idx, app in enumerate(apps, 1):
        anchor = f"app-{app['name'].lower().replace(' ', '-')}"
        arch_badges = " ".join([f"`{a}`" for a in app["arch"]])
        md += f"
"
        md += f"#### {idx}. [{app['name']}](https://github.com/{GITHUB_USER}/{app['repo']})

"
        md += f"{app['description']}

"
        md += "| Parameter | Details |
| :--- | :--- |
"
        md += f"| **Version** | `{app['version']}` |
"
        md += f"| **Architectures** | {arch_badges} |
"
        md += f"| **Community Stats** | ⭐ `{app['stars']}` Stars \| 🐛 `{app['issues']}` Issues |
"
        md += f"| **Documentation** | [📚 Open Repository](https://github.com/{GITHUB_USER}/{app['repo']}) |

---

"
    return md

def build_integrations_block(integrations):
    if not integrations:
        return "*No custom integrations registered yet.*
"
    
    md = "### 📋 Custom Integrations Index

"
    for idx, integ in enumerate(integrations, 1):
        anchor = f"integration-{integ['name'].lower().replace(' ', '-')}"
        md += f"{idx}. [{integ['name']}](#{anchor}) — *v{integ['version']}*
"
    
    md += "
### 🧩 Available Custom Integrations

"
    for idx, integ in enumerate(integrations, 1):
        anchor = f"integration-{integ['name'].lower().replace(' ', '-')}"
        md += f"
"
        md += f"#### {idx}. [{integ['name']}](https://github.com/{GITHUB_USER}/{integ['repo']})

"
        md += f"{integ['description']}

"
        md += "| Parameter | Details |
| :--- | :--- |
"
        md += f"| **Version** | `{integ['version']}` |
"
        md += f"| **Domain** | `{integ['domain']}` |
"
        md += f"| **IoT Class** | `{integ['iot_class']}` |
"
        md += f"| **Community Stats** | ⭐ `{integ['stars']}` Stars \| 🐛 `{integ['issues']}` Issues |
"
        md += f"| **Documentation** | [📚 Open Repository](https://github.com/{GITHUB_USER}/{integ['repo']}) |

---

"
    return md

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="ecosystem", choices=["apps", "integrations", "ecosystem"])
    args = parser.parse_args()

    apps = parse_apps()
    integrations = parse_integrations()

    if args.mode == "apps":
        header = f"# 🚀 Home Assistant Applications & Add-ons Store

Welcome to the official Home Assistant Add-ons repository maintained by [@{GITHUB_USER}](https://github.com/{GITHUB_USER}).

---

"
        content = header + build_apps_block(apps)
    elif args.mode == "integrations":
        header = f"# 🧩 Home Assistant Custom Integrations Catalog

Welcome to the official Home Assistant Custom Components catalog for HACS maintained by [@{GITHUB_USER}](https://github.com/{GITHUB_USER}).

---

"
        content = header + build_integrations_block(integrations)
    else: # ecosystem
        header = f"# 🌐 Home Assistant Master Ecosystem

Welcome to the central portal of [@{GITHUB_USER}](https://github.com/{GITHUB_USER})'s Home Assistant ecosystem. This repository unifies all custom applications, add-ons, and HACS integrations in one place.

---

"
        apps_section = "## 📦 Home Assistant Applications & Add-ons

" + build_apps_block(apps)
        integrations_section = "## 🧩 Home Assistant Custom Integrations

" + build_integrations_block(integrations)
        content = header + apps_section + integrations_section

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Successfully generated README.md for mode '{args.mode}'.")

if __name__ == "__main__":
    main()

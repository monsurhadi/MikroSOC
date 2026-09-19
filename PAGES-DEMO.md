## Apply this update package

Extract this ZIP and copy its contents into your existing MikroSOC repository folder. Replace the root README.md when prompted. Include the `.github` folder. This is an update package, not a standalone Python installation.

From your repository folder in PowerShell:

```powershell
git add README.md PAGES-DEMO.md showcase .github/workflows/pages-demo.yml
git commit -m "Add interactive Pages showcase and detailed README"
git push origin main
```

Then follow the Pages activation instructions below. If your working branch is not main, merge these changes into main first.

# Publish the MikroSOC showcase

The `showcase/` directory is a standalone browser demo. It uses synthetic documentation-range addresses, not your real router or PC addresses. It needs no Python, database, router, account or credentials. It does not modify the Flask application in `mikrosoc/`.

## Publish

1. Merge the showcase files and `.github/workflows/pages-demo.yml` into `main`.
2. Open https://github.com/monsurhadi/MikroSOC/settings/pages .
3. Under Build and deployment, change Source from **Deploy from a branch** to **GitHub Actions**. This replaces the current README-based publishing source.
4. Open the repository's **Actions** tab, select **Deploy MikroSOC showcase**, and choose **Run workflow → main → Run workflow**. Later changes to `showcase/` deploy automatically.
5. Wait for the job to succeed, then open https://monsurhadi.github.io/MikroSOC/ . If an old README remains, use Ctrl+F5 after verifying that the deployment succeeded.

The workflow uploads only `showcase/`; it never publishes your backend, database, configuration or certificates. Do not enable other Pages deployment workflows at the same time. A custom domain already configured in GitHub may change the displayed URL.

## Interactions

- Open Overview, Alerts, Incidents, Devices, Logs, Rules, Reports and Audit trail.
- Acknowledge an alert, save incident notes, change a stage and mark a sample device trusted.
- Try simulated containment with the displayed confirmation text. No network operation occurs.
- Export a CSV generated locally. Files have DEMO in their names.
- Edit sample rule settings. Existing fixtures do not get re-detected; this is a workflow demonstration.
- Changes are saved under `mikrosoc-showcase-v1` in this browser's localStorage. Use Reset demo to restore samples. If browser storage is unavailable, changes last only for the current page session.

No Wazuh or Suricata monitoring is represented as implemented. The demo showcases the existing router-focused MikroSOC features. Do not enter actual passwords or sensitive investigation notes into a public demo.

## Local preview

From the repository root run `python -m http.server 8080 --bind 127.0.0.1` and open http://127.0.0.1:8080/showcase/ . Relative asset paths work under the GitHub project URL too.

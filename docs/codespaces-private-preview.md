# Open your private Auvylen preview in GitHub Codespaces

This uses the existing Phase 4B website and verified MobileNetV3 milestone. No VPS,
Windows server, public deployment or new model development is involved. A GitHub
Codespace has not been purchased or created for you: you choose it under your own
included usage. The real preview URL is assigned when you create the Codespace.

## First launch in GitHub

1. Sign in to GitHub as the owner of the private repository. Check **Settings → Billing
   and licensing** for available included Codespaces compute/storage. Keep paid usage
   disabled; if GitHub requires payment or your quota is exhausted, stop rather than buy.
2. Open [opsevener-cmd/auvylen](https://github.com/opsevener-cmd/auvylen). Choose branch
   **codex/phase4b-custom-preferences**. Do not use the default Phase 4A branch.
3. Click **Code → Codespaces → … → New with options**. Confirm that branch and
   **Auvylen private preview** / `.devcontainer/devcontainer.json`. Choose the **2-core,
   8 GB** machine and click **Create codespace**, using your personal included quota.
4. Wait for creation/setup to finish. It installs locked dependencies, initializes the
   private database, restores/verifies the licensed model and builds the existing website.
   The first launch takes several minutes; later resumes reuse these files.
5. Open the **Ports** tab in the browser editor. Port **3000** should be the only app
   port forwarded. Confirm its **Visibility is Private**, then click **Open in Browser**.
   Do not select Public or Organization. The URL is
   `https://YOUR-CODESPACE-NAME-3000.app.github.dev`.
6. Register an Auvylen account in that website. In the **Codespace terminal**, run:

   ```sh
   python scripts/codespaces-preview.py grant YOUR_REGISTERED_USERNAME
   ```

7. Return to **Research → Personal preference datasets**. Create a project/dataset,
   upload authorized adult photographs with provenance/retention/consent, and save your
   numerical ratings. Use shared person/group IDs for photographs of the same adult.
   Choose **Pretrained MobileNetV3-Small**, then **Train new version**. At least 8 ratings
   and 5 independent groups are required. Select a saved version and a new uploaded
   image to predict. Add annotations and train again to create another version.

The one terminal grant is intentional operator authorization; registration alone never
allows research. Ordinary dataset/annotation/model tasks then use the existing website.
No model weights, database ports or public operator API are exposed.

## Privacy and HTTPS

[GitHub forwards ports privately by default](https://docs.github.com/en/codespaces/reference/security-in-github-codespaces),
requiring Codespace-owner GitHub authentication. Keep that setting. This configuration
forwards only 3000 and ignores automatic forwarding of all other ports. PostgreSQL and
Redis have no host-published ports and use an internal network; FastAPI binds to loopback
8000 inside the workspace. The existing Next.js allow-listed `/api` proxy carries your
session cookie, Origin and CSRF token to FastAPI.

The port's internal **protocol is HTTP** because Next.js listens on HTTP; GitHub provides
external **HTTPS**. Do not change the internal protocol to HTTPS. Session cookies remain
Secure, HttpOnly and SameSite=Lax. The allowed Origin is derived exactly from the current
Codespace name, without wildcard CORS, forwarded-host trust or a public-pilot setting.
Wrong origins and missing CSRF tokens are rejected. Commercial/mock checkout is disabled;
research mode requires an explicit grant and never spends Credits.

The preview is available while the Codespace is running. It is a personal development
preview, with the existing account/annotation limitations and retention rules, not a
permanent production host. No real face dataset is automatically downloaded. The reviewed
ImageNet model restoration downloads only the licensed public checkpoint/dependencies.

## Start, stop and resume

Run these commands **only in the GitHub Codespace terminal**:

```sh
python scripts/codespaces-preview.py status
python scripts/codespaces-preview.py stop
python scripts/codespaces-preview.py start
```

`stop` stops Next.js, FastAPI and the worker while retaining accounts, annotations, models,
private files and database/cache volumes. It does not stop the Codespace's compute.
To suspend cloud compute, open [Your Codespaces](https://github.com/codespaces), find this
Codespace, click **… → Stop codespace**. Closing the website alone is insufficient.
Stopped Codespaces still occupy storage from your included allowance.

To resume, open that **same Codespace** from the Codespaces list. `postStartCommand`
starts the three application processes automatically, including stale-socket recovery
following container termination. If necessary run `start` manually, then open private
port 3000 again. Database/cache and private artifacts survive normal stop/start and the
container-recreation sequence verified by this project. Unfinished leased research jobs
follow the existing retry/fencing policy after resume. Dataset expiry still applies;
physical cleanup waits for the worker when the Codespace is stopped.

Never delete the Codespace or run `docker compose down -v`/volume pruning to stop it.
Back up before rebuilding (especially a full rebuild), updating code, or deleting it.
To re-run first-time dependency/model setup after an intentional update:

```sh
python scripts/codespaces-preview.py setup
python scripts/codespaces-preview.py start
```

No creation lifecycle runs on Windows. Do not open this dev container using local Docker
Desktop; create it through GitHub's web Codespaces interface.

## Encrypted backup

```sh
python scripts/codespaces-preview.py backup
```

Enter a strong backup passphrase in the terminal; save it separately. The command briefly
stops the app/worker, takes a PostgreSQL 18 logical dump and a matching private-file snapshot,
encrypts the archive with GPG/AES256, deletes temporary plaintext and resumes the app if
it was running. It saves a protected `.tar.gz.gpg` and ciphertext SHA-256 under
`backups/codespaces/`. The backup includes database/annotations/jobs/accounts, private
uploads, personal checkpoints, the pretrained graph/notices and matching app secrets.
It excludes package caches, logs and virtual environments. A browser test decrypted the
archive, compared private file bytes and successfully restored the database in isolation.

Keep a verified encrypted copy in approved private storage **outside this Codespace**
before deleting it. Never commit it, upload it to repository assets or publish it. Keep
its passphrase safe; source Git commits are not backups of private data. Retain backups
only as permitted by your photograph permissions/retention strategy and propagate deletion.
GitHub storage is temporary and can be deleted by retention policy. Do not keep essential
private data solely in this development environment.

## Recovery into a new, unused Codespace

Use only your own trusted encrypted backup. Restore into a newly created preview with
**no accounts or research data**, never over an existing populated preview. Preserve its
fresh PostgreSQL credential; restore the original app pepper and private artifacts.
The preview Origin is regenerated for the new Codespace.

Place the encrypted file in ignored `backups/`, then run the following in its terminal
(adjust only `backup_file`):

```sh
private-data/codespaces/venv/bin/python - <<'PY'
import getpass, importlib.util, json, os, shutil, subprocess, tarfile, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location('preview', 'scripts/codespaces-preview.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
data, origin, secret_dir = p.context(); env = p.environment(data, origin, secret_dir)
current = json.loads((data / 'credentials.json').read_text())
env['PGPASSWORD'] = current['postgres_password']
query = ['psql', '-h', 'postgres', '-U', 'aevyra', '-d', 'aevyra', '-Atc',
         'SELECT (SELECT count(*) FROM users)+(SELECT count(*) FROM orders)']
if subprocess.check_output(query, env=env).strip() != b'0':
    raise SystemExit('Destination contains data; use a fresh unused Codespace')
backup_file = Path('backups/YOUR-BACKUP.tar.gz.gpg')
p.stop(data)
with tempfile.TemporaryDirectory(dir=data) as temporary:
    temp = Path(temporary); archive = temp / 'backup.tar.gz'
    passphrase = getpass.getpass('Backup passphrase: ')
    subprocess.run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase-fd', '0',
                    '--output', str(archive), '--decrypt', str(backup_file)],
                   input=(passphrase+'\n').encode(), check=True)
    with tarfile.open(archive) as tar:
        if any(m.name.split('/')[0] not in {'database.dump','credentials.json','uploads','models'}
               or m.issym() or m.islnk() for m in tar.getmembers()):
            raise SystemExit('Unexpected backup contents')
        tar.extractall(temp, filter='data')
    subprocess.run(['pg_restore', '--exit-on-error', '--clean', '--if-exists', '--no-owner',
                    '--no-acl', '-h', 'postgres', '-U', 'aevyra', '-d', 'aevyra',
                    str(temp/'database.dump')], env=env, check=True)
    for name in ('uploads','models'):
        shutil.rmtree(data/name); shutil.copytree(temp/name, data/name)
    current['pepper'] = json.loads((temp/'credentials.json').read_text())['pepper']
    (data/'credentials.json').write_text(json.dumps(current)); os.chmod(data/'credentials.json',0o600)
print('Restore complete. Run the normal start command.')
PY
python scripts/codespaces-preview.py start
```

If recovery fails, keep the new preview stopped and retain the encrypted backup. Do not
rotate credentials or erase the original Codespace to make a failed restore appear clean.

## Verified scope

The devcontainer image, first-time dependency/model restoration, one-edge HTTPS browser
flow, explicit grant, CSRF/cookie/privacy checks, numerical training/versioning/prediction,
container/database resume and encrypted backup/database restoration were executed in
remote Codex Linux. The test TLS edge simulates GitHub HTTPS termination and forwards
**all routes through Next.js**. It is confined to remote loopback and is not installed
in the actual Codespaces configuration.

GitHub's actual Codespace allocation, account quota and private-port login cannot be
verified without you creating a Codespace. No live Codespaces URL is claimed yet. See
[the verification report](codespaces-preview-report.md) for actual test results.

Official references: [creation](https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository),
[port forwarding](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace),
[stop/resume](https://docs.github.com/en/codespaces/developing-in-a-codespace/stopping-and-starting-a-codespace),
[included usage](https://docs.github.com/en/codespaces/troubleshooting/troubleshooting-included-usage).

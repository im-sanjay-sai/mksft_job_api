# Microsoft Job Watcher

Small Python watcher for Microsoft Careers. It polls every 15 minutes by
default, looks only at United States postings, and prints new jobs where:

- `software engineer` appears in the title or job description
- the parsed experience requirement has a minimum value less than or equal to 4 years

The script uses the public Microsoft Careers search endpoint and each job's
public detail page. It stores seen job IDs in SQLite so repeat runs do not print
the same job again.

## Requirements

- Linux machine
- Python 3.9 or newer
- Internet access

No Python packages are required.

## Run once

```bash
cd microsoft-job-watcher
python3 microsoft_job_watcher.py --once
```

## Run forever

```bash
cd microsoft-job-watcher
python3 microsoft_job_watcher.py
```

By default it polls every 15 minutes.

## Useful options

```bash
python3 microsoft_job_watcher.py --once --max-pages 20
python3 microsoft_job_watcher.py --interval-minutes 5
python3 microsoft_job_watcher.py --include-unknown-years
python3 microsoft_job_watcher.py --reset-cache --once
```

Options:

- `--interval-minutes`: poll interval. Default: `15`.
- `--max-pages`: number of Microsoft search pages to read. Microsoft returns
  10 jobs per page. Default: `10`.
- `--max-years`: max acceptable years of experience. Default: `4`.
- `--keyword`: keyword or phrase to match in title/description. Default:
  `software engineer`.
- `--include-unknown-years`: print jobs even when the script cannot find an
  experience requirement. Default is conservative and excludes unknown years.
- `--reset-cache`: delete the seen-job cache before running.

## Run with systemd

Copy the project to a stable location, for example:

```bash
sudo mkdir -p /opt/microsoft-job-watcher
sudo cp microsoft_job_watcher.py /opt/microsoft-job-watcher/
```

Then copy `systemd/microsoft-job-watcher.service` to:

```bash
/etc/systemd/system/microsoft-job-watcher.service
```

Edit the `User`, `Group`, and paths in the service file, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now microsoft-job-watcher
sudo journalctl -u microsoft-job-watcher -f
```

## Notes on the years filter

Microsoft descriptions are prose, not a strict structured field. The script
extracts phrases like `2+ years software industry experience` and accepts the
job when the minimum parsed years value is less than or equal to `--max-years`.
This catches common Microsoft phrasing such as:

- Master's degree and 1+ years
- Bachelor's degree and 2+ years
- 2+ years programming experience

If a posting has no parseable years requirement, it is skipped unless
`--include-unknown-years` is set.

#!/bin/bash -l
# SCC batch job: run the scraper headless and write pages to project space.
#
#   qsub -P <project> data_pipeline/scc/scrape.sh                 # default: categories 1,2
#   qsub -P <project> -v CATS=10 data_pipeline/scc/scrape.sh      # another category
#
# [verify] module name/version (`module avail python3`) and the project space path below.
# The run is resumable: if the job hits its time limit, just submit it again.

#$ -N scrape
#$ -l h_rt=06:00:00
#$ -j y
#$ -o scrape_$JOB_ID.log

set -euo pipefail
module load python3/3.12.4        # [verify]

REPO="${REPO:-$HOME/ml-web-scraping-knowledge}"
PROJECT_SPACE="${PROJECT_SPACE:-/projectnb/<project>/scrape}"   # [verify] fill in the team's project
CATS="${CATS:-1,2}"

cd "$REPO"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
source .venv/bin/activate

# SCRAPER_CONTACT comes from $REPO/.env (not committed). Scraped text stays in project space.
export SCRAPER_OUT="$PROJECT_SPACE"
python -m data_pipeline.scraper parse
python -m data_pipeline.scraper run --category "$CATS"
python -m data_pipeline.scraper report

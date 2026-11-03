# Scrape summary

73 of 388 manifest URLs attempted; 56 usable (`ok`).

## Status by category

| status | cat 1 | cat 2 | cat 10 | total |
|---|---|---|---|---|
| ok | 16 | 40 | 0 | 56 |
| blocked_robots | 0 | 6 | 0 | 6 |
| bot_challenge | 0 | 6 | 0 | 6 |
| http_error | 0 | 1 | 0 | 1 |
| non_html_skipped | 0 | 1 | 0 | 1 |
| paywall_or_login | 0 | 1 | 0 | 1 |
| too_short | 0 | 2 | 0 | 2 |
| _not attempted_ | 139 | 49 | 127 | 315 |

## Usable docs per domain

**Category 1** (16 docs, 8 domains): challengerinc.com 2, meddicc.com 2, trailhead.salesforce.com 2, forcemanagement.com 2, huthwaiteinternational.com 2, salesforce.com 2, handbook.gitlab.com 2, blog.hubspot.com 2

**Category 2** (40 docs, 34 domains): sec.gov 2, dock.us 2, alexandergroup.com 2, insight.kellogg.northwestern.edu 2, gainsight.com 2, leandata.com 2, apollo.io 1, bls.gov 1, presalescollective.com 1, techtarget.com 1, investors.yubico.com 1, blog.workday.com 1, single-market-economy.ec.europa.eu 1, middlemarketcenter.org 1, sba.gov 1, viola-group.com 1, cloud.substack.com 1, pipeline.zoominfo.com 1, revengine.substack.com 1, saascmopro.substack.com 1, theleapadvisor.substack.com 1, saastr.com 1, yesware.com 1, go.forrester.com 1, bain.com 1, customersuccesscollective.com 1, fticonsulting.com 1, news.darden.virginia.edu 1, resources.rework.com 1, revopscoop.substack.com 1, gong.io 1, churnzero.com 1, blog.bridgegroupinc.com 1, revopsinflection.substack.com 1

## Top failing domains

| domain | failures | reasons |
|---|---|---|
| mckinsey.com | 2 | blocked_robots: robots.txt unreachable: timeout (x2) |
| gtmnow.com | 2 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x2) |
| blogs.partner.microsoft.com | 1 | blocked_robots: robots.txt unreachable: SSLError: HTTPSConnectionPool(host='blogs.partner.microsoft.com', port=443): Max retries exceeded with url: /robots.txt (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)'))) (x1) |
| blog.bridgegroupinc.com | 1 | paywall_or_login: login form with only 182 words (x1) |
| kylewill.medium.com | 1 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x1) |
| langfuse.com | 1 | blocked_robots: robots.txt unreachable: timeout (x1) |
| posthog.com | 1 | blocked_robots: robots.txt unreachable: timeout (x1) |
| census.gov | 1 | too_short: 45 words < 150 (x1) |
| fedsmallbusiness.org | 1 | too_short: 91 words < 150 (x1) |
| gartner.com | 1 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x1) |
| cms.implementconsultinggroup.com | 1 | http_error: HTTP 404 (x1) |
| media-publications.bcg.com | 1 | non_html_skipped: PDF (skipped for MVP) (x1) |
| strategyand.pwc.com | 1 | bot_challenge: HTTP 403; bot challenge page ('access denied') (x1) |
| salesforceben.com | 1 | blocked_robots: disallowed by robots.txt (x1) |
| dspace.lib.cranfield.ac.uk | 1 | bot_challenge: HTTP 403; bot challenge page ('attention required! | cloudflare') (x1) |

## Word counts (ok docs)

min 258, median 951, max 124008

| words | docs |
|---|---|
| <500 | 11 |
| 500-1999 | 32 |
| 2000-4999 | 11 |
| 5000+ | 2 |

## Domains whose terms of service haven't been reviewed

A human should check these and mark them `tos_reviewed: true` or `skip: true` in `scraper/domains.yaml`.

alexandergroup.com, apollo.io, bain.com, blog.bridgegroupinc.com, blog.hubspot.com, blog.workday.com, blogs.partner.microsoft.com, bls.gov, census.gov, challengerinc.com, churnzero.com, cloud.substack.com, cms.implementconsultinggroup.com, customersuccesscollective.com, dock.us, dspace.lib.cranfield.ac.uk, fedsmallbusiness.org, forcemanagement.com, fticonsulting.com, gainsight.com, gartner.com, go.forrester.com, gong.io, gtmnow.com, handbook.gitlab.com, huthwaiteinternational.com, insight.kellogg.northwestern.edu, investors.yubico.com, kylewill.medium.com, langfuse.com, leandata.com, mckinsey.com, meddicc.com, media-publications.bcg.com, middlemarketcenter.org, news.darden.virginia.edu, pipeline.zoominfo.com, posthog.com, presalescollective.com, resources.rework.com, revengine.substack.com, revopscoop.substack.com, revopsinflection.substack.com, saascmopro.substack.com, saastr.com, salesforce.com, salesforceben.com, sba.gov, sec.gov, single-market-economy.ec.europa.eu, strategyand.pwc.com, techtarget.com, theleapadvisor.substack.com, trailhead.salesforce.com, viola-group.com, yesware.com

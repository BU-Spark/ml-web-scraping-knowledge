# Scrape summary

412 of 412 manifest URLs attempted; 356 usable (`ok`).

## Status by category

| status | cat 1 | cat 2 | cat 10 | total |
|---|---|---|---|---|
| ok | 150 | 105 | 101 | 356 |
| blocked_robots | 0 | 8 | 12 | 20 |
| bot_challenge | 0 | 6 | 10 | 16 |
| duplicate_content | 0 | 2 | 0 | 2 |
| http_error | 0 | 3 | 4 | 7 |
| non_html_skipped | 0 | 1 | 0 | 1 |
| paywall_or_login | 0 | 1 | 0 | 1 |
| redirected_away | 1 | 2 | 0 | 3 |
| too_short | 4 | 2 | 0 | 6 |
| _not attempted_ | 0 | 0 | 0 | 0 |

## Usable docs per domain

**Category 1** (150 docs, 8 domains): forcemanagement.com 75, trailhead.salesforce.com 17, meddicc.com 15, huthwaiteinternational.com 13, salesforce.com 13, challengerinc.com 7, handbook.gitlab.com 7, blog.hubspot.com 3

**Category 2** (105 docs, 44 domains): salesforce.com 21, handbook.gitlab.com 7, alexandergroup.com 7, sec.gov 6, trailhead.salesforce.com 5, blog.hubspot.com 5, dock.us 4, gainsight.com 4, leandata.com 4, pipeline.zoominfo.com 3, cloud.substack.com 3, claude.com 3, insight.kellogg.northwestern.edu 2, apollo.io 1, bls.gov 1, presalescollective.com 1, techtarget.com 1, investors.yubico.com 1, blog.workday.com 1, single-market-economy.ec.europa.eu 1, middlemarketcenter.org 1, sba.gov 1, viola-group.com 1, abmatic.ai 1, revengine.substack.com 1, saascmopro.substack.com 1, theleapadvisor.substack.com 1, saastr.com 1, yesware.com 1, go.forrester.com 1, bain.com 1, customersuccesscollective.com 1, fticonsulting.com 1, salesfolks.com 1, news.darden.virginia.edu 1, resources.rework.com 1, revopscoop.substack.com 1, gong.io 1, spotio.com 1, syncgtm.com 1, churnzero.com 1, blog.bridgegroupinc.com 1, revopsinflection.substack.com 1, openai.com 1

**Category 10** (101 docs, 45 domains): trainingindustry.com 8, salesenablementcollective.com 8, forrester.com 5, chieflearningofficer.com 5, accent-technologies.com 4, seismic.com 4, contentmarketinginstitute.com 3, rainsalestraining.com 3, gong.io 3, allego.com 3, showpad.com 3, bain.com 3, highspot.com 2, salesforce.com 2, productmarketingalliance.com 2, mindtickle.com 2, community.highspot.com 2, elearningindustry.com 2, revenue.io 2, salesloft.com 2, kornferry.com 2, saleshood.com 2, techtarget.com 2, insight.kellogg.northwestern.edu 2, frontiersin.org 2, bcg.com 2, revopscoop.com 2, winningbydesign.com 2, kirkpatrickpartners.com 1, blog.hubspot.com 1, uxcontent.com 1, learn.g2.com 1, earley.com 1, articulate.com 1, go.forrester.com 1, sellingpower.com 1, ambition.com 1, spotio.com 1, kixie.com 1, salesgrowth.com 1, outreach.ai 1, trailhead.salesforce.com 1, knowledge.wharton.upenn.edu 1, ey.com 1, sbigrowth.com 1

## Top failing domains

| domain | failures | reasons |
|---|---|---|
| gartner.com | 9 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x9) |
| mckinsey.com | 8 | blocked_robots: robots.txt unreachable: ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) (x8) |
| forcemanagement.com | 5 | too_short: 103 words < 150 (x1); redirected_away: redirected to generic page https://www.ascender.co/ (x1); too_short: 135 words < 150 (x1) |
| salesforce.com | 4 | redirected_away: redirected to generic page https://www.salesforce.com/resources/?bc=DB (x1); redirected_away: redirected to generic page https://www.salesforce.com/in/resources/?bc=DB (x1); duplicate_content: same content as 2d0ec1fe6adab77c (x1) |
| gtmnow.com | 3 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x3) |
| mdpi.com | 3 | blocked_robots: robots.txt returned HTTP 403 (x3) |
| umbrex.com | 2 | http_error: HTTP 403 (x2) |
| jiminny.com | 2 | blocked_robots: disallowed by robots.txt (x2) |
| blogs.partner.microsoft.com | 1 | blocked_robots: robots.txt unreachable: SSLError: HTTPSConnectionPool(host='blogs.partner.microsoft.com', port=443): Max retries exceeded with url: /robots.txt (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)'))) (x1) |
| blog.bridgegroupinc.com | 1 | paywall_or_login: login form with only 182 words (x1) |
| kylewill.medium.com | 1 | bot_challenge: HTTP 403; bot challenge page ('just a moment...') (x1) |
| langfuse.com | 1 | blocked_robots: robots.txt unreachable: timeout (x1) |
| posthog.com | 1 | blocked_robots: robots.txt unreachable: timeout (x1) |
| census.gov | 1 | too_short: 137 words < 150 (x1) |
| fedsmallbusiness.org | 1 | too_short: 91 words < 150 (x1) |
| cms.implementconsultinggroup.com | 1 | http_error: HTTP 404 (x1) |
| media-publications.bcg.com | 1 | non_html_skipped: PDF (skipped for MVP) (x1) |
| strategyand.pwc.com | 1 | bot_challenge: HTTP 403; bot challenge page ('access denied') (x1) |
| salesforceben.com | 1 | blocked_robots: disallowed by robots.txt (x1) |
| dspace.lib.cranfield.ac.uk | 1 | bot_challenge: HTTP 403; bot challenge page ('attention required! | cloudflare') (x1) |

## Word counts (ok docs)

min 168, median 1151, max 13005

| words | docs |
|---|---|
| <500 | 54 |
| 500-1999 | 226 |
| 2000-4999 | 67 |
| 5000+ | 9 |

## Domains whose terms of service haven't been reviewed

A human should check these and mark them `tos_reviewed: true` or `skip: true` in `data_pipeline/scraper/domains.yaml`.

abmatic.ai, accent-technologies.com, alexandergroup.com, allego.com, ambition.com, apollo.io, articulate.com, bain.com, bcg.com, blog.bridgegroupinc.com, blog.hubspot.com, blog.workday.com, blogs.partner.microsoft.com, bls.gov, census.gov, challengerinc.com, chieflearningofficer.com, churnzero.com, claude.com, cloud.substack.com, cms.implementconsultinggroup.com, community.highspot.com, contentmarketinginstitute.com, customersuccesscollective.com, dock.us, dspace.lib.cranfield.ac.uk, earley.com, elearningindustry.com, enterprisetimes.co.uk, ey.com, fedsmallbusiness.org, forbes.com, forcemanagement.com, forrester.com, frontiersin.org, fticonsulting.com, gainsight.com, gartner.com, go.forrester.com, gong.io, gtmnow.com, handbook.gitlab.com, highspot.com, huthwaiteinternational.com, insight.kellogg.northwestern.edu, investors.yubico.com, jiminny.com, kirkpatrickpartners.com, kixie.com, knowledge.insead.edu, knowledge.wharton.upenn.edu, kornferry.com, kylewill.medium.com, langfuse.com, leandata.com, learn.g2.com, mckinsey.com, mdpi.com, meddicc.com, media-publications.bcg.com, middlemarketcenter.org, mindtickle.com, news.darden.virginia.edu, news.mays.tamu.edu, openai.com, outreach.ai, pipeline.zoominfo.com, posthog.com, presalescollective.com, productmarketingalliance.com, rainsalestraining.com, resources.rework.com, revengine.substack.com, revenue.io, revopscoop.com, revopscoop.substack.com, revopsinflection.substack.com, saascmopro.substack.com, saastr.com, salesenablementcollective.com, salesfolks.com, salesforce.com, salesforceben.com, salesgrowth.com, saleshood.com, salesloft.com, sba.gov, sbigrowth.com, sec.gov, seismic.com, sellingpower.com, showpad.com, single-market-economy.ec.europa.eu, spotio.com, strategyand.pwc.com, syncgtm.com, techtarget.com, theleapadvisor.substack.com, trailhead.salesforce.com, trainingindustry.com, umbrex.com, uxcontent.com, venturebeat.com, viola-group.com, winningbydesign.com, yesware.com

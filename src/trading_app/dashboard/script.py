"""Operator dashboard browser script.

This file is the single source of truth for client-side behavior:

- Hash-routed screen switching (#home / #models / #paper / #risk / #research / #ai).
- Periodic snapshot refresh via /api/snapshot (5s cadence).
- Operator control POSTs to /api/control.
- Hero area-chart redraw on period change.

Keep dependency-free (no framework). Tests assert on substrings here.
"""

from __future__ import annotations


def script() -> str:
    """Return the interactive dashboard script tag content."""

    return _SCRIPT


_SCRIPT = """
  <script>
    // -----------------------------------------------------------------
    // utilities
    // -----------------------------------------------------------------
    function money(value) {
      const number = Number(value || 0);
      return number.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
    }
    function escapeHtml(value) {
      const text = value === undefined || value === null ? '' : String(value);
      const replacements = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
      return text.replace(/[&<>"']/g, (char) => replacements[char]);
    }
    function setText(field, value) {
      document.querySelectorAll(`[data-field="${field}"]`).forEach((node) => {
        node.textContent = value === undefined || value === null ? '' : String(value);
      });
    }
    function setTone(field, baseClass, tone) {
      document.querySelectorAll(`[data-field="${field}"]`).forEach((node) => {
        node.className = `${baseClass} ${tone}`.trim();
      });
    }
    function setControlDisabled(action, disabled) {
      document.querySelectorAll(`[data-control-action="${action}"]`).forEach((node) => {
        node.disabled = disabled;
      });
    }
    function enumValue(value, fallback) {
      if (!value) return fallback;
      if (typeof value === 'object' && value.value) return value.value;
      return value;
    }
    function yesNo(value) { return value ? 'yes' : 'no'; }

    // -----------------------------------------------------------------
    // nav routing — hash-based single-page nav
    // -----------------------------------------------------------------
    const SCREENS = ['home', 'strategies', 'paper', 'risk', 'research', 'ai'];

    function activateScreen(name) {
      const target = SCREENS.includes(name) ? name : 'home';
      document.querySelectorAll('[data-screen]').forEach((node) => {
        const matches = node.dataset.screen === target;
        node.hidden = !matches;
      });
      document.querySelectorAll('[data-screen-link]').forEach((node) => {
        if (node.dataset.screenLink === target) {
          node.setAttribute('aria-current', 'page');
        } else {
          node.removeAttribute('aria-current');
        }
      });
      const titleNode = document.querySelector('[data-screen-title]');
      if (titleNode) {
        titleNode.textContent = titleNode.dataset[`title_${target}`] || titleNode.textContent;
      }
      window.scrollTo({ top: 0 });
    }

    function currentScreenFromHash() {
      const raw = (window.location.hash || '').replace(/^#\\/?/, '').toLowerCase();
      return SCREENS.includes(raw) ? raw : 'home';
    }

    function wireNav() {
      document.querySelectorAll('[data-screen-link]').forEach((node) => {
        node.addEventListener('click', (event) => {
          event.preventDefault();
          const target = node.dataset.screenLink;
          if (window.location.hash !== '#' + target) {
            window.location.hash = '#' + target;
          } else {
            activateScreen(target);
          }
        });
      });
      window.addEventListener('hashchange', () => activateScreen(currentScreenFromHash()));
      activateScreen(currentScreenFromHash());
    }

    // -----------------------------------------------------------------
    // hero area chart — built from snapshot.cash + estimated_equity
    // -----------------------------------------------------------------
    function buildHeroSeries(snapshot) {
      const cash = Number(snapshot.cash || 0);
      const equity = Number(snapshot.estimated_equity || cash);
      const start = cash;
      const mid = (cash + equity) / 2;
      const dip = equity * 0.997;
      return [start, mid, equity, dip, equity];
    }

    function renderHeroChart(snapshot) {
      const target = document.querySelector('[data-hero-chart]');
      if (!target) return;
      const values = buildHeroSeries(snapshot);
      const w = target.clientWidth || 800;
      const h = target.clientHeight || 280;
      const padL = 16, padR = 16, padT = 14, padB = 28;
      const innerW = w - padL - padR;
      const innerH = h - padT - padB;
      const min = Math.min.apply(null, values);
      const max = Math.max.apply(null, values);
      const spread = Math.max(max - min, 0.0001);
      const points = values.map((value, index) => {
        const x = padL + (index / (values.length - 1)) * innerW;
        const y = padT + innerH - ((value - min) / spread) * innerH;
        return [x, y];
      });
      const baselineY = padT + innerH;
      const linePath = 'M ' + points.map((p) => p[0].toFixed(2) + ' ' + p[1].toFixed(2)).join(' L ');
      const areaPath = linePath + ' L ' + points[points.length - 1][0].toFixed(2) + ' ' + baselineY.toFixed(2)
        + ' L ' + points[0][0].toFixed(2) + ' ' + baselineY.toFixed(2) + ' Z';
      const positive = values[values.length - 1] >= values[0];
      const series = positive ? 'pos' : 'neg';
      const gridY = [0.25, 0.5, 0.75].map((frac) => {
        const y = padT + innerH * frac;
        return `<line class="grid-line" x1="${padL}" x2="${padL + innerW}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" />`;
      }).join('');
      const labels = ['', '', '', '', 'now'].map((text, index) => {
        const x = padL + (index / (values.length - 1)) * innerW;
        if (!text) return '';
        return `<text class="axis-text" x="${x.toFixed(1)}" y="${(h - 10).toFixed(1)}" text-anchor="end">${text}</text>`;
      }).join('');
      const last = points[points.length - 1];
      target.innerHTML = `
        <svg class="area-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Paper equity curve">
          <defs>
            <linearGradient id="fill-pos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#2bd576" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#2bd576" stop-opacity="0" />
            </linearGradient>
            <linearGradient id="fill-neg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#ff4d5e" stop-opacity="0.24" />
              <stop offset="100%" stop-color="#ff4d5e" stop-opacity="0" />
            </linearGradient>
          </defs>
          ${gridY}
          <path d="${areaPath}" class="fill-${series}" />
          <path d="${linePath}" class="line-${series}" />
          <circle class="end-dot ${positive ? '' : 'neg'}" cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="3.5" />
          ${labels}
        </svg>`;
    }

    function wirePeriods() {
      document.querySelectorAll('[data-period]').forEach((node) => {
        node.addEventListener('click', () => {
          document.querySelectorAll('[data-period]').forEach((n) => n.setAttribute('aria-pressed', 'false'));
          node.setAttribute('aria-pressed', 'true');
          // Period switching currently re-renders the same demo series. The
          // hook is in place for when historical series land in the snapshot.
          if (window.__lastSnapshot) renderHeroChart(window.__lastSnapshot);
        });
      });
    }

    // -----------------------------------------------------------------
    // latest prices
    // -----------------------------------------------------------------
    function latestPriceData(snapshot) {
      const runtimeLatest = snapshot.runtime_state && snapshot.runtime_state.latest_prices;
      if (runtimeLatest) {
        return {
          status: enumValue(runtimeLatest.status, 'missing'),
          feed: enumValue(runtimeLatest.feed, 'unavailable'),
          warning: runtimeLatest.warning || 'Latest prices are available.',
          prices: runtimeLatest.prices || []
        };
      }
      const marketData = snapshot.session_state && snapshot.session_state.market_data;
      if (marketData) {
        return {
          status: enumValue(marketData.status, 'missing'),
          feed: enumValue(marketData.feed, 'unavailable'),
          warning: marketData.warning || 'Latest prices are available.',
          prices: Object.entries(marketData.prices || {}).map(([symbol, price]) => ({
            symbol, price, status: enumValue(marketData.status, 'fresh')
          }))
        };
      }
      return { status: 'missing', feed: 'unavailable', warning: 'Latest prices have not refreshed yet.', prices: [] };
    }

    function renderLatestPrices(snapshot) {
      const target = document.querySelector('[data-latest-price-list]');
      const latest = latestPriceData(snapshot);
      setText('price-freshness', latest.status);
      setText('price-feed', latest.feed);
      setText('price-warning', latest.warning);
      if (!target) return;
      if (!latest.prices.length) {
        target.innerHTML = '<p class="empty">No latest prices available yet.</p>';
        return;
      }
      target.innerHTML = latest.prices.map((record) => {
        const status = enumValue(record.status, 'missing');
        const tone = status === 'fresh' ? 'pos' : 'warn';
        return `
          <div class="row">
            <div class="row__primary">${escapeHtml(record.symbol)}<small>${escapeHtml(status)}</small></div>
            <div class="row__value ${tone}">${money(record.price)}</div>
          </div>`;
      }).join('');
    }

    // -----------------------------------------------------------------
    // data quality
    // -----------------------------------------------------------------
    function dataQualityTone(status) {
      if (status === 'failed') return 'pill--danger';
      if (status === 'warning' || status === 'unavailable') return 'pill--warn';
      return 'pill--good';
    }
    function joinValues(values) {
      const rendered = (values || []).map((value) => enumValue(value, value)).filter(Boolean);
      return rendered.length ? rendered.join(', ') : 'unavailable';
    }
    function humanizeCode(value) {
      const acronyms = new Set(['iex', 'sip', 'us', 'etf', 'pnl']);
      return enumValue(value, 'quality_issue').split('_').map((part) => (
        acronyms.has(part) ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)
      )).join(' ');
    }
    function dataQualityWindow(report) {
      if (!report) return 'unavailable';
      const provenance = report.provenance || {};
      if (provenance.start && provenance.end) return `${provenance.start} to ${provenance.end}`;
      return report.generated_at || 'unavailable';
    }
    function renderDataQuality(snapshot) {
      const dailyReport = snapshot.daily_report || {};
      const report = dailyReport.data_quality_report;
      const target = document.querySelector('[data-data-quality-issue-list]');
      if (!report) {
        setText('data-quality-status', 'unavailable');
        setText('data-quality-chip', 'unavailable');
        setTone('data-quality-chip', 'pill', 'pill--warn');
        setText('data-quality-summary', 'No market-data quality report is attached to this dashboard snapshot.');
        setText('data-quality-research-usable', 'unknown');
        setText('data-quality-trading-usable', 'unknown');
        setText('data-quality-warnings', '-');
        setText('data-quality-failures', '-');
        setText('data-quality-dataset', 'unavailable');
        setText('data-quality-symbols', 'unavailable');
        setText('data-quality-sources', 'unavailable');
        setText('data-quality-feeds', 'unavailable');
        setText('data-quality-window', 'unavailable');
        if (target) target.innerHTML = '<p class="empty">No quality report available.</p>';
        return;
      }
      const status = enumValue(report.status, 'unavailable');
      const provenance = report.provenance || {};
      setText('data-quality-status', status);
      setText('data-quality-chip', status);
      setTone('data-quality-chip', 'pill', dataQualityTone(status));
      setText('data-quality-summary', report.summary || 'Market-data quality status is unavailable.');
      setText('data-quality-research-usable', yesNo(report.can_use_for_research));
      setText('data-quality-trading-usable', yesNo(report.can_use_for_trading));
      setText('data-quality-warnings', String(report.warnings || 0));
      setText('data-quality-failures', String(report.failures || 0));
      setText('data-quality-dataset', provenance.dataset_type || 'unavailable');
      setText('data-quality-symbols', (provenance.symbols || []).length ? `${provenance.symbols.length} tracked` : 'unavailable');
      setText('data-quality-sources', joinValues(provenance.sources));
      setText('data-quality-feeds', joinValues(provenance.feeds));
      setText('data-quality-window', dataQualityWindow(report));
      if (!target) return;
      const issues = report.issues || [];
      if (!issues.length) {
        target.innerHTML = '<p class="empty">No quality issues detected.</p>';
        return;
      }
      target.innerHTML = issues.slice(0, 4).map((issue) => {
        const issueStatus = enumValue(issue.status, 'warning');
        const klass = issueStatus === 'failed' ? 'row row--danger' : 'row row--warn';
        let subject = issue.symbol || 'dataset';
        if (issue.trading_date) subject = `${subject} ${issue.trading_date}`;
        return `
          <div class="${klass}">
            <div class="row__primary"><strong>${escapeHtml(humanizeCode(issue.code))}</strong><small>${escapeHtml(issue.message)}</small></div>
            <div class="row__meta">${escapeHtml(subject)}</div>
          </div>`;
      }).join('');
    }

    // -----------------------------------------------------------------
    // alerts
    // -----------------------------------------------------------------
    function renderAlerts(snapshot) {
      const alerts = snapshot.alerts || [];
      const target = document.querySelector('[data-alert-list]');
      const hasError = alerts.some((alert) => enumValue(alert.severity, '') === 'error');
      const tone = hasError ? 'pill--danger' : alerts.length ? 'pill--warn' : 'pill--good';
      setText('alert-count', `${alerts.length} active`);
      setText('alert-tone', hasError ? 'ERROR' : alerts.length ? 'WARN' : 'CLEAR');
      setTone('alert-tone', 'pill', tone);
      if (!target) return;
      if (!alerts.length) {
        target.innerHTML = '<p class="empty">No active alerts.</p>';
        return;
      }
      target.innerHTML = alerts.map((alert) => {
        const severity = enumValue(alert.severity, 'warning');
        const klass = severity === 'error' ? 'row row--danger' : 'row row--warn';
        const code = enumValue(alert.code, 'runtime_alert');
        const evidence = (alert.evidence || []).join(' / ');
        return `
          <div class="${klass}">
            <div class="row__primary"><strong>${escapeHtml(alert.title)}</strong><small>${escapeHtml(alert.message)}</small></div>
            <div class="row__meta">${escapeHtml(code)}</div>
            <div class="row__value warn">${escapeHtml(evidence)}</div>
          </div>`;
      }).join('');
    }

    // -----------------------------------------------------------------
    // positions
    // -----------------------------------------------------------------
    function renderPositions(snapshot) {
      const positions = (((snapshot.paper_report || {}).ledger_snapshot || {}).positions || []);
      const target = document.querySelector('[data-position-list]');
      setText('position-count', `${positions.length} open`);
      if (!target) return;
      if (!positions.length) {
        target.innerHTML = '<p class="empty">No positions.</p>';
        return;
      }
      target.innerHTML = positions.map((position) => `
          <div class="row">
            <div class="row__primary">${escapeHtml(position.symbol)}<small>avg cost</small></div>
            <div class="row__meta mono">${escapeHtml(position.quantity)} sh</div>
            <div class="row__value">${money(position.average_cost)}</div>
          </div>`).join('');
    }

    // -----------------------------------------------------------------
    // fills
    // -----------------------------------------------------------------
    function renderFills(snapshot) {
      const fills = snapshot.recent_fills || [];
      const target = document.querySelector('[data-fill-list]');
      setText('fill-count', String(fills.length));
      if (!target) return;
      if (!fills.length) {
        target.innerHTML = '<p class="empty">No fills.</p>';
        return;
      }
      target.innerHTML = fills.map((fill) => {
        const side = enumValue(fill.side, 'UNKNOWN');
        const tone = side === 'BUY' ? 'pos' : 'neg';
        return `
          <div class="row">
            <div class="row__primary"><strong>${escapeHtml(fill.symbol)}</strong><small>${escapeHtml(fill.filled_at)}</small></div>
            <div class="row__meta ${tone}">${escapeHtml(side)}</div>
            <div class="row__value">${escapeHtml(fill.quantity)} @ ${money(fill.price)}</div>
          </div>`;
      }).join('');
    }

    // -----------------------------------------------------------------
    // health
    // -----------------------------------------------------------------
    function healthTone(status) {
      if (status === 'critical') return 'pill--danger';
      if (status === 'degraded') return 'pill--warn';
      if (status === 'watch') return 'pill--ai';
      return 'pill--good';
    }
    function renderHealth(snapshot) {
      const health = snapshot.health_report;
      if (!health) return;
      const status = enumValue(health.status, 'unknown');
      setText('health-status', status);
      setText('health-incident-count', `${(health.incidents || []).length} incident`);
      setText('health-summary', health.summary || 'Runtime health is unavailable.');
      setText('health-report-path', `Incident review: ${snapshot.health_report_path || 'not written'}`);
      setTone('health-incident-count', 'pill', healthTone(status));
      const checksTarget = document.querySelector('[data-health-check-list]');
      if (checksTarget) {
        const checks = health.checks || [];
        checksTarget.innerHTML = checks.length ? checks.map((check) => {
          const checkStatus = enumValue(check.status, 'unknown');
          const tone = checkStatus === 'healthy' ? 'pos' : checkStatus === 'degraded' ? 'warn' : 'neg';
          return `
          <div class="row">
            <div class="row__primary"><strong>${escapeHtml(check.name)}</strong><small>${escapeHtml(check.message)}</small></div>
            <div class="row__value ${tone}">${escapeHtml(checkStatus)}</div>
          </div>`;
        }).join('') : '<p class="empty">No health checks yet.</p>';
      }
      const incidentTarget = document.querySelector('[data-incident-list]');
      if (incidentTarget) {
        const incidents = health.incidents || [];
        incidentTarget.innerHTML = incidents.length ? incidents.map((incident) => {
          const incidentStatus = enumValue(incident.status, 'watch');
          const klass = incidentStatus === 'critical' ? 'row row--danger' : incidentStatus === 'degraded' ? 'row row--warn' : 'row';
          return `
          <div class="${klass}">
            <div class="row__primary"><strong>${escapeHtml(incident.title)}</strong><small>${escapeHtml(incident.summary)}</small></div>
            <div class="row__meta">${escapeHtml(incidentStatus)}</div>
            <div class="row__value warn">${escapeHtml(incident.suggested_action)}</div>
          </div>`;
        }).join('') : '<p class="empty">No open incidents.</p>';
      }
    }

    // -----------------------------------------------------------------
    // controls
    // -----------------------------------------------------------------
    function renderControls(snapshot) {
      const state = snapshot.control_state || {};
      const paused = Boolean(state.paused);
      const killSwitch = Boolean(snapshot.kill_switch_enabled || state.paper_kill_switch_enabled);
      setText('control-state-heading', paused ? 'Paused' : 'Armed');
      setText('paper-kill-switch-state', `Kill ${killSwitch ? 'ON' : 'OFF'}`);
      setTone('paper-kill-switch-state', 'pill', killSwitch ? 'pill--danger' : 'pill--good');
      document.querySelectorAll('[data-field="kill-switch"]').forEach((node) => {
        node.textContent = `Kill switch ${killSwitch ? 'ON' : 'OFF'}`;
        node.className = killSwitch ? 'pill pill--danger' : 'pill pill--good pill--armed';
      });
      const lastResult = snapshot.last_control_result || {};
      const request = lastResult.request || {};
      setText('last-control-action', enumValue(request.action, 'none'));
      setText('control-updated-by', state.updated_by || 'system');
      setText('control-updated-at', state.updated_at || 'pending');
      setControlDisabled('resume_runtime', !paused);
      setControlDisabled('pause_runtime', paused);
      setControlDisabled('disable_paper_kill_switch', !killSwitch);
      setControlDisabled('enable_paper_kill_switch', killSwitch);
      setControlDisabled('force_reconciliation', false);
      setControlDisabled('generate_report', false);
    }

    // -----------------------------------------------------------------
    // reports / final acceptance / statement review / live readiness
    // -----------------------------------------------------------------
    function renderReports(snapshot) {
      const runtime = snapshot.runtime_state || {};
      const dailyReport = snapshot.daily_report || {};
      const metadata = dailyReport.report_metadata || {};
      const dailyReportPath = runtime.daily_report_path || metadata.markdown_path || 'not written';
      const nightly = snapshot.nightly_learning;
      const learningPath = snapshot.nightly_learning_path || runtime.nightly_learning_path || 'not written';
      const activeModelUnchanged = !nightly || nightly.active_model_unchanged !== false;
      setText('report-status', dailyReportPath === 'not written' ? 'Snapshot' : 'Written');
      setText('daily-report-state', dailyReportPath === 'not written' ? 'snapshot' : 'written');
      setText('daily-report-path', dailyReportPath);
      setText('trading-day', dailyReport.trading_day || 'unknown');
      setText('learning-state', nightly ? 'complete' : 'waiting');
      setText('learning-memo-path', learningPath);
      setText('active-mutation-state', activeModelUnchanged ? 'blocked' : 'review');
    }
    function renderFinalAcceptance(snapshot) {
      const report = snapshot.final_acceptance;
      if (!report) {
        setText('final-acceptance-status', 'Awaiting Signoff');
        setText('final-acceptance-chip', 'Not final');
        setTone('final-acceptance-chip', 'pill', 'pill--warn');
        setText('final-acceptance-accepted', 'no');
        setText('final-acceptance-checks', '0/0');
        setText('final-acceptance-signoff', 'missing');
        setText('final-acceptance-path', 'not written');
        setText('final-acceptance-summary', 'Run final acceptance after operator signoff and reviewed Alpaca Paper evidence.');
        return;
      }
      const accepted = Boolean(report.accepted_for_functional_paper_app);
      const checks = report.checks || [];
      const passed = checks.filter((check) => enumValue(check.status, 'failed') === 'passed').length;
      setText('final-acceptance-status', enumValue(report.status, 'unknown'));
      setText('final-acceptance-chip', accepted ? 'Accepted' : 'Blocked');
      setTone('final-acceptance-chip', 'pill', accepted ? 'pill--good' : 'pill--danger');
      setText('final-acceptance-accepted', accepted ? 'yes' : 'no');
      setText('final-acceptance-checks', `${passed}/${checks.length}`);
      setText('final-acceptance-signoff', report.signoff_path || 'missing');
      setText('final-acceptance-path', report.markdown_path || 'not written');
      setText('final-acceptance-summary', report.summary || 'Final acceptance evidence is available.');
    }
    function renderStatementReview(snapshot) {
      const report = snapshot.statement_reconciliation;
      const target = document.querySelector('[data-statement-issue-list]');
      if (!report) {
        setText('statement-status', 'Awaiting Statement');
        setText('statement-chip', 'Post-run');
        setTone('statement-chip', 'pill', 'pill--warn');
        setText('statement-id', 'not loaded');
        setText('statement-provider', 'unknown');
        setText('statement-issues', 'unknown');
        setText('statement-path', 'not written');
        setText('statement-caveat', 'Paper/research-only review. Not filing-grade tax accounting.');
        if (target) target.innerHTML = '<p class="empty">Run post-run statement reconciliation.</p>';
        return;
      }
      const statement = report.statement || {};
      const issues = report.issues || [];
      const reconciled = Boolean(report.reconciled);
      setText('statement-status', reconciled ? 'Reconciled' : 'Mismatch');
      setText('statement-chip', reconciled ? 'Clean' : 'Review');
      setTone('statement-chip', 'pill', reconciled ? 'pill--good' : 'pill--danger');
      setText('statement-id', statement.statement_id || 'unknown');
      setText('statement-provider', statement.provider || 'unknown');
      setText('statement-issues', String(issues.length));
      setText('statement-path', snapshot.statement_reconciliation_path || 'not written');
      setText('statement-caveat', 'Paper/research-only review. Not filing-grade tax accounting.');
      if (!target) return;
      if (!issues.length) {
        target.innerHTML = '<p class="empty">No statement differences above tolerance.</p>';
        return;
      }
      target.innerHTML = issues.slice(0, 4).map((issue) => {
        const issueType = enumValue(issue.issue_type, 'statement_issue');
        return `
          <div class="row row--danger">
            <div class="row__primary"><strong>${escapeHtml(humanizeCode(issueType.toLowerCase()))}</strong><small>${escapeHtml(issue.message || 'Statement mismatch requires review.')}</small></div>
            <div class="row__meta">${escapeHtml(issue.symbol || 'account')}</div>
          </div>`;
      }).join('');
    }
    function renderLiveReadiness(snapshot) {
      const live = snapshot.live_readiness;
      if (!live) {
        setText('live-readiness-status', 'disabled');
        setText('live-readiness-panel-status', 'disabled');
        return;
      }
      const status = enumValue(live.status, 'blocked');
      const checks = live.checks || [];
      const passed = checks.filter((check) => check.passed).length;
      const limits = live.limits || {};
      setText('live-readiness-status', status);
      setText('live-readiness-panel-status', status);
      setText('live-readiness-checks', `${passed}/${checks.length}`);
      setText('live-max-order', money(limits.max_order_notional));
      setText('live-approved-models', String((live.approved_model_keys || []).length));
    }
    function renderRuntimeProof(snapshot) {
      const runtime = snapshot.runtime_state || {};
      const cycle = runtime.last_cycle || {};
      const session = snapshot.session_state || {};
      const modelCards = snapshot.model_cards || [];
      const fallbackModel = modelCards.length ? `${modelCards[0].strategy_id}:${modelCards[0].version}` : 'unassigned';
      let brokerConnection = 'awaiting';
      if (runtime.last_cycle) {
        brokerConnection = cycle.broker_synced ? 'connected' : 'degraded';
      } else if (session.connection_status) {
        brokerConnection = enumValue(session.connection_status, 'awaiting');
      }
      setText('runtime-status', enumValue(runtime.status, 'awaiting'));
      setText('prices-refreshed', yesNo(cycle.prices_refreshed));
      setText('broker-synced', yesNo(cycle.broker_synced));
      setText('broker-connection', brokerConnection);
      setText('active-model-key', runtime.active_model_key || fallbackModel);
      setText('trading-authority', 'Daily close only');
      setText('orders-submitted', String(cycle.orders_submitted || 0));
      setText('fills-applied', String(cycle.fills_applied || 0));
    }
    function renderPlainRows(target, values, emptyText) {
      if (!target) return;
      target.innerHTML = values.length ? values.map((value) => `
          <div class="row"><div class="row__primary"><small>${escapeHtml(value)}</small></div></div>`).join('') : `<p class="empty">${escapeHtml(emptyText)}</p>`;
    }
    function renderActiveStrategy(snapshot) {
      const definition = snapshot.active_strategy_definition;
      if (!definition) return;
      setText('active-strategy-name', definition.name);
      setText('active-strategy-authority', enumValue(definition.authority, 'paper'));
      setText('active-strategy-hypothesis', definition.hypothesis);
      setText('active-strategy-id', `${definition.strategy_id}:${definition.version}`);
      setText('active-strategy-cadence', enumValue(definition.trading_cadence, 'daily_close'));
      setText('active-strategy-benchmark', definition.benchmark);
      setText('active-strategy-universe', `${(definition.universe || []).length} U.S. ETF(s)`);
      setText('active-strategy-signal', definition.signal_logic);
      setText('active-strategy-sizing', definition.sizing_logic);
      setText('active-strategy-exit', definition.exit_logic);
      renderPlainRows(
        document.querySelector('[data-active-strategy-failure-list]'),
        (definition.failure_modes || []).slice(0, 3),
        'No failure modes recorded.'
      );
      renderPlainRows(
        document.querySelector('[data-active-strategy-ai-role-list]'),
        (definition.ai_role || []).slice(0, 3),
        'No AI role recorded.'
      );
    }

    // -----------------------------------------------------------------
    // snapshot apply (top-level)
    // -----------------------------------------------------------------
    function applySnapshot(snapshot) {
      window.__lastSnapshot = snapshot;
      setText('mode', snapshot.mode);
      setText('broker', snapshot.broker);
      setText('paper-boundary-mode', snapshot.mode);
      setText('estimated-equity', money(snapshot.estimated_equity));
      setText('cash', money(snapshot.cash));
      setText('realized-pnl', money(snapshot.realized_pnl));
      setText('open-orders', String(snapshot.open_orders));
      const reconciled = snapshot.paper_report && snapshot.paper_report.reconciliation && snapshot.paper_report.reconciliation.reconciled;
      setText('reconciliation', reconciled ? 'Reconciled' : 'Mismatch');
      const risk = snapshot.daily_report && snapshot.daily_report.risk_report;
      if (risk) {
        setText('risk-severity', enumValue(risk.severity, 'unknown'));
      }
      const completion = snapshot.completion_audit;
      if (completion) {
        setText('completion-status', enumValue(completion.status, 'unknown'));
        setText('completion-chip', completion.passed ? 'Ready' : 'Evidence');
        setText('completion-proven', String(completion.proven_count || 0));
        setText('completion-missing', String(completion.missing_count || 0));
        setText('completion-failed', String(completion.failed_count || 0));
        setText('completion-external', String(completion.external_required_count || 0));
        setText('completion-path', completion.markdown_path || 'not written');
        setText('completion-summary', completion.summary || 'Completion audit evidence is available.');
      }
      const tax = snapshot.daily_report && snapshot.daily_report.tax_report;
      if (tax) {
        setText('tax-active-lots', String(tax.active_lot_count || 0));
        setText('tax-realized-lots', String(tax.realized_lot_count || 0));
        setText('tax-lot-method', enumValue(tax.lot_method, 'fifo').toUpperCase());
        setText('tax-short-term-gains', money(tax.short_term_realized_gains));
        setText('tax-long-term-gains', money(tax.long_term_realized_gains));
        setText('tax-total-gains', money(tax.total_realized_gains));
        setText('tax-estimated-tax', tax.tax_estimate_available ? money(tax.estimated_tax) : 'unavailable');
        setText('tax-estimate-state', tax.tax_estimate_available ? 'available' : 'estimate only');
      }
      renderRuntimeProof(snapshot);
      renderActiveStrategy(snapshot);
      renderLatestPrices(snapshot);
      renderDataQuality(snapshot);
      renderAlerts(snapshot);
      renderPositions(snapshot);
      renderFills(snapshot);
      renderHealth(snapshot);
      renderControls(snapshot);
      renderReports(snapshot);
      renderFinalAcceptance(snapshot);
      renderStatementReview(snapshot);
      renderLiveReadiness(snapshot);
      renderHeroChart(snapshot);
    }

    async function refreshDashboardSnapshot() {
      try {
        const response = await fetch('/api/snapshot', { cache: 'no-store' });
        if (!response.ok) return;
        const snapshot = await response.json();
        const generated = document.querySelector('[data-refresh-time]');
        if (generated) generated.textContent = ` ${snapshot.generated_at}`;
        applySnapshot(snapshot);
        document.documentElement.dataset.dashboardMode = snapshot.mode;
      } catch (_error) {
        document.documentElement.dataset.dashboardMode = 'refresh-error';
      }
    }

    async function sendOperatorControl(action) {
      const response = await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, requested_by: 'local-dashboard', reason: 'dashboard control' })
      });
      if (response.ok) window.location.reload();
    }

    document.querySelectorAll('[data-control-action]').forEach((button) => {
      button.addEventListener('click', () => sendOperatorControl(button.dataset.controlAction));
    });

    // -----------------------------------------------------------------
    // Plain / Technical vocabulary toggle (Phase B1)
    // -----------------------------------------------------------------
    function setVocab(vocab) {
      const value = vocab === 'technical' ? 'technical' : 'plain';
      document.documentElement.dataset.vocab = value;
      try { window.localStorage.setItem('dashVocab', value); } catch (_e) { /* private mode */ }
      document.querySelectorAll('[data-vocab-set]').forEach((btn) => {
        btn.setAttribute('aria-pressed', btn.dataset.vocabSet === value ? 'true' : 'false');
      });
    }
    function wireVocabToggle() {
      let stored = 'plain';
      try { stored = window.localStorage.getItem('dashVocab') || 'plain'; } catch (_e) { /* ignore */ }
      setVocab(stored);
      document.querySelectorAll('[data-vocab-set]').forEach((btn) => {
        btn.addEventListener('click', () => setVocab(btn.dataset.vocabSet));
      });
    }

    // -----------------------------------------------------------------
    // First-time tour (Phase B2)
    // -----------------------------------------------------------------
    let __tourStep = 0;
    function tourCards() { return Array.from(document.querySelectorAll('[data-tour-step]')); }
    function clearSpotlight() {
      document.querySelectorAll('[data-tour-spotlight]').forEach((el) => {
        delete el.dataset.tourSpotlight;
      });
    }
    function positionTourCard(card, target) {
      // Pin the card to viewport-bottom on the same horizontal half as the
      // target. Keeps it visible regardless of scroll position.
      const rect = target.getBoundingClientRect();
      const onLeftHalf = rect.left + rect.width / 2 < window.innerWidth / 2;
      card.style.bottom = '24px';
      card.style.top = 'auto';
      if (onLeftHalf) { card.style.left = '24px'; card.style.right = 'auto'; }
      else { card.style.right = '24px'; card.style.left = 'auto'; }
    }
    function showTourStep(index) {
      const cards = tourCards();
      if (!cards.length) return;
      clearSpotlight();
      cards.forEach((c) => { c.hidden = true; });
      const card = cards[index];
      if (!card) return endTour();
      const selector = card.dataset.tourTarget;
      const target = selector ? document.querySelector(selector) : null;
      if (target) {
        target.dataset.tourSpotlight = '1';
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        positionTourCard(card, target);
      }
      card.hidden = false;
      __tourStep = index;
    }
    function beginTour() {
      // Always start on Home so the hero target is on screen.
      if (window.location.hash !== '#home') window.location.hash = '#home';
      const wrap = document.querySelector('[data-tour]');
      if (!wrap) return;
      wrap.hidden = false;
      wrap.setAttribute('aria-hidden', 'false');
      showTourStep(0);
    }
    function endTour() {
      const wrap = document.querySelector('[data-tour]');
      clearSpotlight();
      if (wrap) {
        wrap.hidden = true;
        wrap.setAttribute('aria-hidden', 'true');
        tourCards().forEach((c) => { c.hidden = true; });
      }
      try { window.localStorage.setItem('dashTourSeen', '1'); } catch (_e) { /* ignore */ }
    }
    function wireTour() {
      document.querySelectorAll('[data-tour-next]').forEach((btn) => {
        btn.addEventListener('click', () => {
          if (__tourStep + 1 >= tourCards().length) endTour();
          else showTourStep(__tourStep + 1);
        });
      });
      document.querySelectorAll('[data-tour-skip]').forEach((btn) => {
        btn.addEventListener('click', endTour);
      });
      document.addEventListener('keydown', (event) => {
        const wrap = document.querySelector('[data-tour]');
        if (!wrap || wrap.hidden) return;
        if (event.key === 'Escape') endTour();
        else if (event.key === 'ArrowRight' || event.key === 'Enter') {
          if (__tourStep + 1 >= tourCards().length) endTour();
          else showTourStep(__tourStep + 1);
        }
      });
      document.querySelectorAll('[data-tour-start]').forEach((btn) => {
        btn.addEventListener('click', beginTour);
      });
      // Auto-start for first-time users.
      let seen = '';
      try { seen = window.localStorage.getItem('dashTourSeen') || ''; } catch (_e) { /* ignore */ }
      if (!seen) {
        // Wait one tick so layout is settled.
        window.setTimeout(beginTour, 200);
      }
    }

    wireNav();
    wirePeriods();
    wireVocabToggle();
    wireTour();
    refreshDashboardSnapshot();
    window.setInterval(refreshDashboardSnapshot, 5000);
  </script>"""

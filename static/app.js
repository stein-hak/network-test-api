const API_BASE = window.location.origin;

// Tab switching
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    event.target.classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');

    if (tabName === 'scheduled') {
        loadScheduledTests();
    } else if (tabName === 'workers') {
        checkWorkerIPs();
    }
}

// Manual Tests
async function testVLESS(event) {
    event.preventDefault();

    const vlessUrl = document.getElementById('vless-url').value;
    const timeout = parseInt(document.getElementById('vless-timeout').value);
    const resultsDiv = document.getElementById('vless-results');

    resultsDiv.innerHTML = '<div class="loading">Testing...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/test/vless/async`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vless_url: vlessUrl, timeout })
        });

        const data = await response.json();

        if (data.job_id) {
            resultsDiv.innerHTML = `<div class="alert alert-info">Job submitted: ${data.job_id}</div>`;
            pollJobResults(data.job_id, resultsDiv);
        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${JSON.stringify(data)}</div>`;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

async function testSubscription(event) {
    event.preventDefault();

    const subscriptionUrl = document.getElementById('sub-url').value;
    const timeout = parseInt(document.getElementById('sub-timeout').value);
    const testVlessLinks = document.getElementById('test-links').checked;
    const maxLinksToTest = parseInt(document.getElementById('max-links').value);
    const resultsDiv = document.getElementById('sub-results');

    resultsDiv.innerHTML = '<div class="loading">Testing...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/test/subscription/async`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subscription_url: subscriptionUrl,
                timeout,
                test_vless_links: testVlessLinks,
                max_links_to_test: maxLinksToTest
            })
        });

        const data = await response.json();

        if (data.job_id) {
            resultsDiv.innerHTML = `<div class="alert alert-info">Job submitted: ${data.job_id}</div>`;
            pollJobResults(data.job_id, resultsDiv);
        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${JSON.stringify(data)}</div>`;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

async function testConnectivity(event) {
    event.preventDefault();

    const target = document.getElementById('conn-target').value;
    const port = parseInt(document.getElementById('conn-port').value);
    const protocol = document.getElementById('conn-protocol').value;
    const resultsDiv = document.getElementById('conn-results');

    resultsDiv.innerHTML = '<div class="loading">Testing...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/test/connectivity/async`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target, port, protocol, timeout: 10 })
        });

        const data = await response.json();

        if (data.job_id) {
            resultsDiv.innerHTML = `<div class="alert alert-info">Job submitted: ${data.job_id}</div>`;
            pollJobResults(data.job_id, resultsDiv);
        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${JSON.stringify(data)}</div>`;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

async function testSSL(event) {
    event.preventDefault();

    const domain = document.getElementById('ssl-domain').value;
    const port = parseInt(document.getElementById('ssl-port').value);
    const resultsDiv = document.getElementById('ssl-results');

    resultsDiv.innerHTML = '<div class="loading">Testing...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/test/ssl/async`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ domain, port, timeout: 10 })
        });

        const data = await response.json();

        if (data.job_id) {
            resultsDiv.innerHTML = `<div class="alert alert-info">Job submitted: ${data.job_id}</div>`;
            pollJobResults(data.job_id, resultsDiv);
        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${JSON.stringify(data)}</div>`;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

// Poll job results
async function pollJobResults(jobId, resultsDiv) {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/orchestrator/job/${jobId}`);

            if (!response.ok) {
                clearInterval(interval);
                const text = await response.text();
                resultsDiv.innerHTML = `<div class="alert alert-error">API error (${response.status}): ${text}</div>`;
                return;
            }

            const job = await response.json();

            if (job.status === 'completed' || job.status === 'failed') {
                clearInterval(interval);
                displayJobResults(job, resultsDiv);
            } else {
                resultsDiv.innerHTML = `
                    <div class="alert alert-info">
                        Status: ${job.status} - Progress: ${job.progress}%<br>
                        Workers: ${job.total_workers} total
                    </div>
                `;
            }
        } catch (error) {
            clearInterval(interval);
            resultsDiv.innerHTML = `<div class="alert alert-error">Polling error: ${error.message}</div>`;
        }
    }, 2000);
}

function displayJobResults(job, resultsDiv) {
    const statusClass = job.status === 'completed' ? 'success' : 'error';

    let html = `
        <div class="alert alert-${statusClass}">
            <strong>Status:</strong> ${job.status}<br>
            <strong>Workers:</strong> ${job.successful}/${job.total_workers} successful
        </div>
        <div class="worker-grid">
    `;

    job.worker_results.forEach(result => {
        const workerStatus = result.test_result?.success ? 'success' : 'failed';
        html += `
            <div class="worker-card ${workerStatus}">
                <div class="worker-url">${result.worker_url}</div>
                <div class="worker-status status-${result.status}">${result.status}</div>
        `;

        if (result.test_result) {
            if (result.test_result.latency_ms !== null) {
                html += `<div>Latency: ${result.test_result.latency_ms}ms</div>`;
            }
            if (result.test_result.external_ip) {
                html += `<div>IP: ${result.test_result.external_ip}</div>`;
            }
            if (result.test_result.link_count) {
                html += `<div>Links: ${result.test_result.link_count}</div>`;
            }
            if (result.test_result.tested_links) {
                const successCount = result.test_result.tested_links.filter(l => l.success).length;
                html += `<div>Tested: ${successCount}/${result.test_result.tested_links.length} OK</div>`;
            }
            if (result.test_result.error) {
                html += `<div style="color: #e74c3c; font-size: 12px;">${result.test_result.error}</div>`;
            }
        }

        html += `</div>`;
    });

    html += `</div>`;
    resultsDiv.innerHTML = html;
}

// Scheduled Tests
function updateScheduledForm() {
    const testType = document.getElementById('sched-type').value;
    const paramsDiv = document.getElementById('sched-params');

    let html = '';

    if (testType === 'subscription') {
        html = `
            <div class="form-group">
                <label>Subscription URL</label>
                <input type="text" id="sched-param-url" placeholder="https://example.com/sub/user123" required>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="sched-param-test-links" checked>
                <label for="sched-param-test-links">Test VLESS links</label>
            </div>
            <div class="form-group">
                <label>Max links to test</label>
                <input type="number" id="sched-param-max-links" value="3" min="0">
            </div>
            <div class="form-group">
                <label>Timeout (seconds)</label>
                <input type="number" id="sched-param-timeout" value="30" min="5" max="120">
            </div>
        `;
    } else if (testType === 'vless') {
        html = `
            <div class="form-group">
                <label>VLESS URL</label>
                <textarea id="sched-param-url" required></textarea>
            </div>
            <div class="form-group">
                <label>Timeout (seconds)</label>
                <input type="number" id="sched-param-timeout" value="20" min="5" max="60">
            </div>
        `;
    } else if (testType === 'connectivity') {
        html = `
            <div class="form-group">
                <label>Target (domain or IP)</label>
                <input type="text" id="sched-param-target" placeholder="example.com" required>
            </div>
            <div class="form-group">
                <label>Port</label>
                <input type="number" id="sched-param-port" value="443" min="1" max="65535">
            </div>
            <div class="form-group">
                <label>Protocol</label>
                <select id="sched-param-protocol">
                    <option value="https">HTTPS</option>
                    <option value="http">HTTP</option>
                    <option value="tcp">TCP</option>
                </select>
            </div>
        `;
    } else if (testType === 'ssl') {
        html = `
            <div class="form-group">
                <label>Domain</label>
                <input type="text" id="sched-param-domain" placeholder="example.com" required>
            </div>
            <div class="form-group">
                <label>Port</label>
                <input type="number" id="sched-param-port" value="443" min="1" max="65535">
            </div>
        `;
    }

    paramsDiv.innerHTML = html;
}

function updateScheduleFields() {
    const scheduleType = document.getElementById('sched-schedule-type').value;
    document.getElementById('sched-interval-field').style.display = scheduleType === 'interval' ? 'block' : 'none';
    document.getElementById('sched-cron-field').style.display = scheduleType === 'cron' ? 'block' : 'none';
}

async function createScheduledTest(event) {
    event.preventDefault();

    const testType = document.getElementById('sched-type').value;
    const name = document.getElementById('sched-name').value;
    const scheduleType = document.getElementById('sched-schedule-type').value;
    const enabled = document.getElementById('sched-enabled').checked;

    let requestData = { name, enabled };

    if (scheduleType === 'interval') {
        requestData.interval_hours = parseInt(document.getElementById('sched-interval').value);
    } else {
        requestData.cron_expression = document.getElementById('sched-cron').value;
    }

    // Add test-specific parameters
    if (testType === 'subscription') {
        requestData.subscription_url = document.getElementById('sched-param-url').value;
        requestData.test_vless_links = document.getElementById('sched-param-test-links').checked;
        requestData.max_links_to_test = parseInt(document.getElementById('sched-param-max-links').value);
        requestData.timeout = parseInt(document.getElementById('sched-param-timeout').value);
    } else if (testType === 'vless') {
        requestData.vless_url = document.getElementById('sched-param-url').value;
        requestData.timeout = parseInt(document.getElementById('sched-param-timeout').value);
    } else if (testType === 'connectivity') {
        requestData.target = document.getElementById('sched-param-target').value;
        requestData.port = parseInt(document.getElementById('sched-param-port').value);
        requestData.protocol = document.getElementById('sched-param-protocol').value;
        requestData.timeout = 10;
    } else if (testType === 'ssl') {
        requestData.domain = document.getElementById('sched-param-domain').value;
        requestData.port = parseInt(document.getElementById('sched-param-port').value);
        requestData.timeout = 10;
    }

    try {
        const response = await fetch(`${API_BASE}/orchestrator/scheduled/${testType}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (response.ok) {
            alert(`Scheduled test created successfully: ${data.scheduled_id}`);
            loadScheduledTests();
            event.target.reset();
        } else {
            alert(`Error: ${JSON.stringify(data)}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function loadScheduledTests() {
    const listDiv = document.getElementById('scheduled-list');
    listDiv.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/scheduled`);
        const data = await response.json();

        if (data.scheduled_tests && data.scheduled_tests.length > 0) {
            let html = '';
            data.scheduled_tests.forEach(test => {
                const badge = test.enabled ?
                    '<span class="badge enabled">Enabled</span>' :
                    '<span class="badge disabled">Disabled</span>';

                html += `
                    <div class="scheduled-item">
                        <div class="scheduled-info">
                            <h4>${test.name} ${badge}</h4>
                            <div class="scheduled-meta">
                                Type: ${test.task_type} |
                                Schedule: ${test.schedule} |
                                Runs: ${test.run_count} |
                                Last: ${test.last_run || 'Never'}
                            </div>
                        </div>
                        <div class="scheduled-actions">
                            <button onclick="viewScheduledTest('${test.id}')" class="secondary">View</button>
                            <button onclick="toggleScheduledTest('${test.id}', ${!test.enabled})" class="secondary">
                                ${test.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button onclick="deleteScheduledTest('${test.id}')" class="danger">Delete</button>
                        </div>
                    </div>
                `;
            });
            listDiv.innerHTML = html;
        } else {
            listDiv.innerHTML = '<div class="alert alert-info">No scheduled tests found</div>';
        }
    } catch (error) {
        listDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

async function viewScheduledTest(id) {
    try {
        const response = await fetch(`${API_BASE}/orchestrator/scheduled/${id}`);
        const data = await response.json();

        let resultText = '';
        if (data.last_job_result) {
            resultText = `\n\nLast Job Results:\n${JSON.stringify(data.last_job_result, null, 2)}`;
        } else {
            resultText = '\n\nNo recent results (job not run or expired from Redis)';
        }

        alert(`Scheduled Test Details:\n\nName: ${data.name}\nType: ${data.task_type}\nSchedule: ${data.schedule}\nEnabled: ${data.enabled}\nRuns: ${data.run_count}\nLast Run: ${data.last_run_at || 'Never'}${resultText}`);
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function toggleScheduledTest(id, enabled) {
    try {
        const response = await fetch(`${API_BASE}/orchestrator/scheduled/${id}/enable?enabled=${enabled}`, {
            method: 'PUT'
        });

        if (response.ok) {
            loadScheduledTests();
        } else {
            const data = await response.json();
            alert(`Error: ${JSON.stringify(data)}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function deleteScheduledTest(id) {
    if (!confirm('Are you sure you want to delete this scheduled test?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/orchestrator/scheduled/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadScheduledTests();
        } else {
            const data = await response.json();
            alert(`Error: ${JSON.stringify(data)}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

// Worker Status
async function checkWorkerIPs() {
    const ipsDiv = document.getElementById('worker-ips');
    ipsDiv.innerHTML = '<div class="loading">Checking workers...</div>';

    try {
        const response = await fetch(`${API_BASE}/orchestrator/check-all-ips`);
        const data = await response.json();

        if (data.workers) {
            let html = '';
            data.workers.forEach(worker => {
                html += `
                    <div class="worker-card success">
                        <div class="worker-url">${worker.worker_url}</div>
                        <div><strong>IP:</strong> ${worker.ip}</div>
                        <div><strong>Location:</strong> ${worker.location || 'Unknown'}</div>
                    </div>
                `;
            });
            ipsDiv.innerHTML = html;
        } else {
            ipsDiv.innerHTML = '<div class="alert alert-error">No workers found</div>';
        }
    } catch (error) {
        ipsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    }
}

// Initialize
updateScheduledForm();

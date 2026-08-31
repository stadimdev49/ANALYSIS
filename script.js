let cachedParsedData = [];
let cachedYears = [];
let cachedAllNums = [];
let cachedOverallFreq = {};
let cachedOverallDelays = {};
let cachedYearlyFreq = {};
let cachedYearlyDelays = {};

function switchTab(tabIndex) {
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
    document.getElementById(`tab-content-${tabIndex}`).classList.remove('hidden');

    document.querySelectorAll('.tab-btn').forEach((btn, idx) => {
        if (idx + 1 === tabIndex) {
            btn.className = "tab-btn active py-3.5 px-5 font-bold text-sm border-b-2 border-emerald-500 text-emerald-700 bg-emerald-100/60 transition-all flex items-center gap-2 rounded-t-xl";
        } else {
            btn.className = "tab-btn py-3.5 px-5 font-semibold text-sm border-b-2 border-transparent text-slate-600 hover:text-emerald-800 transition-all flex items-center gap-2";
        }
    });

    // Διασφάλιση ότι θα γίνει render ο πίνακας ή περιεχόμενο αν επιλεγεί το Tab 2 ή Tab 3
    if (tabIndex === 2 && cachedAllNums.length > 0) {
        renderTab2();
    } else if (tabIndex === 3 && cachedParsedData.length > 0) {
        populateTab3();
    }
}

function switchGame() {
    loadData(false);
}

function getSelectedGame() {
    return document.querySelector('input[name="gameType"]:checked').value;
}

function showProgress(show, text = "Γίνεται λήψη κληρώσεων...") {
    const container = document.getElementById('progressContainer');
    const txt = document.getElementById('progressText');
    if (txt) txt.textContent = text;
    if (container) {
        if (show) {
            container.classList.remove('hidden');
        } else {
            container.classList.add('hidden');
        }
    }
}

async function downloadAndRefresh() {
    const gameType = getSelectedGame();
    const btn = document.getElementById('downloadBtn');
    if (btn) btn.disabled = true;
    showProgress(true, `Λήψη πλήρους ιστορικού για ${gameType.toUpperCase()}... Παρακαλώ περιμένετε.`);

    try {
        let res = await fetch(`/api/download-draws/${gameType}`, { method: 'POST' });
        let result = await res.json();
        if (result.status === 'success') {
            await loadData(true);
        } else {
            alert("Σφάλμα: " + result.message);
        }
    } catch (e) {
        alert("Αποτυχία επικοινωνίας με τον server.");
    } finally {
        if (btn) btn.disabled = false;
        showProgress(false);
    }
}

async function loadData(forceRefresh = false) {
    const gameType = getSelectedGame();
    showProgress(true, "Φόρτωση δεδομένων...");
    try {
        let res = await fetch(`/api/load-draws/${gameType}`);
        let jsonRes = await res.json();
        
        let rawData = jsonRes.draws || jsonRes;
        let lastUpdate = jsonRes.last_update || "Άγνωστη";

        const updateTextElem = document.getElementById('lastUpdateText');
        if (updateTextElem) {
            updateTextElem.textContent = lastUpdate;
        }

        if (!rawData || rawData.length === 0) {
            if (!forceRefresh) {
                await downloadAndRefresh();
                return;
            }
        }
        processAndDisplay(rawData, gameType);
    } catch (e) {
        console.error("Σφάλμα φόρτωσης:", e);
    } finally {
        showProgress(false);
    }
}

function processAndDisplay(rawData, gameType) {
    const maxNum = gameType === 'joker' ? 45 : 49;
    cachedAllNums = Array.from({length: maxNum}, (_, i) => i + 1);

    cachedParsedData = rawData.map(d => {
        let did = d.drawId || d.drawNo || 0;
        let draw_time = d.drawTime;
        let dt;
        if (typeof draw_time === 'number') {
            dt = new Date(draw_time > 1e12 ? draw_time : draw_time * 1000);
        } else {
            dt = new Date(draw_time || d.date || Date.now());
        }
        
        let winning_numbers = d.winningNumbers || {};
        let numbers = winning_numbers.list || d.results || [];
        if(!numbers.length && d.numbers) numbers = d.numbers;

        return {
            draw_id: did,
            date: dt,
            year: dt.getFullYear() || 2024,
            numbers: numbers.sort((a,b)=>a-b)
        };
    }).sort((a,b) => b.draw_id - a.draw_id);

    let flatAll = cachedParsedData.flatMap(d => d.numbers);
    cachedOverallFreq = {};
    cachedAllNums.forEach(n => cachedOverallFreq[n] = 0);
    flatAll.forEach(n => { if(cachedOverallFreq[n] !== undefined) cachedOverallFreq[n]++; });

    cachedOverallDelays = {};
    cachedAllNums.forEach(num => {
        let idx = cachedParsedData.findIndex(d => d.numbers.includes(num));
        cachedOverallDelays[num] = idx !== -1 ? idx : cachedParsedData.length;
    });

    cachedYears = [...new Set(cachedParsedData.map(d => d.year))].sort((a,b)=>b-a);
    cachedYearlyFreq = {};
    cachedYearlyDelays = {};

    cachedYears.forEach(y => {
        let yDraws = cachedParsedData.filter(d => d.year === y);
        let yFlat = yDraws.flatMap(d => d.numbers);
        cachedYearlyFreq[y] = {};
        cachedYearlyDelays[y] = {};
        cachedAllNums.forEach(num => {
            cachedYearlyFreq[y][num] = yFlat.filter(n => n === num).length;
            let idx = yDraws.findIndex(d => d.numbers.includes(num));
            cachedYearlyDelays[y][num] = idx !== -1 ? idx : yDraws.length;
        });
    });

    const yearSelect = document.getElementById('yearFilter');
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="all">Συνολικά (Όλα τα έτη)</option>';
        cachedYears.forEach(y => {
            yearSelect.innerHTML += `<option value="${y}">Έτος ${y}</option>`;
        });
    }

    populateTab1();
    renderTab2();
    populateTab3();
}

function populateTab1() {
    const tbody = document.getElementById('table1-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    let last10 = cachedParsedData.slice(0, 10);

    if (last10.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-12 text-center text-slate-500">Δεν βρέθηκαν δεδομένα κληρώσεων. Πατήστε "Λήψη Πλήρους Ιστορικού".</td></tr>`;
        return;
    }

    last10.forEach((draw, i) => {
        let preceding10 = cachedParsedData.slice(i + 1, i + 11);
        let flatPreceding = preceding10.flatMap(d => d.numbers);
        let countsPreceding = {};
        flatPreceding.forEach(n => countsPreceding[n] = (countsPreceding[n] || 0) + 1);

        let catSummary = {0: [], 1: [], 2: [], "3+": []};
        draw.numbers.forEach(n => {
            let c = countsPreceding[n] || 0;
            if(c === 0) catSummary[0].push(n);
            else if(c === 1) catSummary[1].push(n);
            else if(c === 2) catSummary[2].push(n);
            else catSummary["3+"].push(n);
        });

        let catDesc = Object.entries(catSummary).filter(([k,v]) => v.length > 0).map(([k,v]) => `<span class="px-2 py-0.5 rounded bg-emerald-100 text-xs font-semibold text-emerald-900 border border-emerald-300">Κατηγ. ${k}: ${v.join(', ')}</span>`);
        
        let numDetails = draw.numbers.map(n => {
            let prevDist = null;
            for(let j = i + 1; j < cachedParsedData.length; j++) {
                if(cachedParsedData[j].numbers.includes(n)) {
                    prevDist = j - i;
                    break;
                }
            }
            return prevDist !== null ? `Αρ.${n} (<span class="text-emerald-700 font-bold">${prevDist}κλ</span>)` : `Αρ.${n} (<span class="text-amber-700 font-bold">πρώτη</span>)`;
        });

        let tr = document.createElement('tr');
        tr.className = "hover:bg-emerald-50/60 transition";
        tr.innerHTML = `
            <td class="p-4 text-center font-bold text-slate-800">${draw.draw_id}</td>
            <td class="p-4 text-center text-slate-600 text-xs">${draw.date ? draw.date.toISOString().split('T')[0] : ''}</td>
            <td class="p-4"><div class="flex gap-1.5 flex-wrap">${draw.numbers.map(n => `<span class="number-pill">${n}</span>`).join('')}</div></td>
            <td class="p-4"><div class="flex gap-1.5 flex-wrap">${catDesc.join(' ')}</div></td>
            <td class="p-4 text-xs text-slate-600">${numDetails.join(' | ')}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderTab2() {
    const tbody = document.getElementById('table2-body');
    if (!tbody) return;
    const yearSelect = document.getElementById('yearFilter');
    const selectedYear = yearSelect ? yearSelect.value : "all";
    tbody.innerHTML = '';

    if (cachedAllNums.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-12 text-center text-slate-500">Δεν υπάρχουν δεδομένα για εμφάνιση.</td></tr>`;
        return;
    }

    cachedAllNums.forEach(num => {
        let freq, delay;
        if (selectedYear === "all") {
            freq = cachedOverallFreq[num] || 0;
            delay = cachedOverallDelays[num] || 0;
        } else {
            let y = parseInt(selectedYear);
            freq = cachedYearlyFreq[y]?.[num] || 0;
            delay = cachedYearlyDelays[y]?.[num] || 0;
        }

        let tr = document.createElement('tr');
        tr.className = "hover:bg-emerald-50/60 transition";
        tr.innerHTML = `
            <td class="p-4 text-center font-bold text-emerald-800 text-base">${num}</td>
            <td class="p-4 text-center font-semibold text-slate-800">${cachedOverallFreq[num] || 0}</td>
            <td class="p-4 text-center font-semibold text-slate-800">${cachedOverallDelays[num] || 0}</td>
            <td class="p-4 text-center font-semibold text-emerald-700">${selectedYear === "all" ? "-" : freq}</td>
            <td class="p-4 text-center font-semibold text-amber-700">${selectedYear === "all" ? "-" : delay}</td>
        `;
        tbody.appendChild(tr);
    });
}

function populateTab3() {
    const container = document.getElementById('analysis-container');
    if (!container) return;
    container.innerHTML = '';

    if (cachedParsedData.length === 0) {
        container.innerHTML = `<div class="p-6 text-center text-slate-500">Δεν υπάρχουν δεδομένα για στατιστικές προτάσεις.</div>`;
        return;
    }

    const last5Draws = cachedParsedData.slice(0, 5);
    const last5Nums = new Set(last5Draws.flatMap(d => d.numbers));

    let htmlContent = `
        <div class="bg-white border border-emerald-200 rounded-2xl p-6 space-y-4 shadow-sm">
            <h3 class="text-base font-bold text-emerald-900 flex items-center gap-2">
                <span>📊</span> Προτάσεις βάσει των τελευταίων 5 κληρώσεων (Συνολικές Εμφανίσεις - 1)
            </h3>
            <p class="text-xs text-slate-600">Αφαιρούμε -1 από τις συνολικές εμφανίσεις των αριθμών που εμφανίστηκαν στις τελευταίες 5 κληρώσεις:</p>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
    `;

    Array.from(last5Nums).sort((a,b)=>a-b).forEach(n => {
        let origFreq = cachedOverallFreq[n] || 0;
        let targetFreq = origFreq - 1;
        let matchingNums = cachedAllNums.filter(cand => cachedOverallFreq[cand] === targetFreq && !last5Nums.has(cand));

        htmlContent += `
            <div class="bg-emerald-50/50 border border-emerald-200/80 rounded-xl p-4 space-y-3 shadow-sm">
                <div class="flex justify-between items-center">
                    <span class="text-sm font-bold text-slate-800 flex items-center gap-2">
                        <span class="number-pill">${n}</span> Αριθμός
                    </span>
                    <span class="text-xs px-2.5 py-1 bg-white border border-emerald-200 rounded-lg text-emerald-900 font-medium">Συνολικές: ${origFreq} &rarr; Στόχος: ${targetFreq}</span>
                </div>
        `;

        if(matchingNums.length > 0) {
            htmlContent += `
                <div class="text-xs text-slate-600 pt-1">Προτεινόμενοι αριθμοί με <strong class="text-emerald-800 font-bold">${targetFreq}</strong> εμφανίσεις:</div>
                <div class="flex gap-1.5 flex-wrap pt-2">${matchingNums.map(mn => `<span class="number-pill bg-emerald-800 text-white">${mn}</span>`).join('')}</div>
            `;
        } else {
            htmlContent += `<div class="text-xs text-amber-800 italic pt-1">⚠️ Δεν υπάρχουν διαθέσιμοι αριθμοί με ${targetFreq} συνολικές εμφανίσεις.</div>`;
        }

        htmlContent += `</div>`;
    });

    htmlContent += `</div></div>`;
    container.innerHTML = htmlContent;
}

window.onload = () => loadData(false);

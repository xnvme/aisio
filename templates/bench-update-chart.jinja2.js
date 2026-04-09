function createRadios(containerId, values, name, prettyName, checkedValue) {
  let label_for = document.querySelector(`[label-for="${name}"]`);
  if (!label_for && name == "hyperthreads") {
    label_for = document.querySelector(`[label-for="ncpus"]`);
  }
  label_for.innerHTML = prettyName;

  const container = document.getElementById(containerId);


  if (!container.children.length) {
    values.forEach(v => {
      const label = document.createElement('label');
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = name;
      radio.value = v;
      label.appendChild(radio);
      if (name === "fixed_freq" && !isNaN(v)) {
        label.appendChild(document.createTextNode(`${v} GHz`));
      } else {
        label.appendChild(document.createTextNode(v));
      }
      container.appendChild(label);
    });
  }

  let defaultChecked = container.querySelector(`input[value="${checkedValue}"]`);
  if (!defaultChecked) {
    defaultChecked = container.querySelector(`input`);
  }
  defaultChecked.checked = true;
}
xValues.forEach(({elemId, set, key, prettyName}, idx) => {
  createRadios(elemId, set, key, prettyName, radioDefaults[idx]);
});
document.querySelectorAll(`input[type="radio"]`).forEach(radio => {
    radio.addEventListener('change', () => updateChart());
});

function updateRadios() {
  xValues.forEach(({elemId, set, key}, i) => {
    let button = document.querySelector(`.controls .button-row.x button[value="${i}"]`);
    if (!button) return;

    const container = document.getElementById(elemId);

    if (i === CUR_X_AXIS) {
      button.classList.add("selected");
      container.previousElementSibling.classList.add("disabled");
    } else {
      button.classList.remove("selected");
      container.previousElementSibling.classList.remove("disabled");
    }
  });

  const query = ".controls .button-row.y button";
  document.querySelectorAll(query).forEach(button => {
    button.classList.remove("selected");
  });
  document.querySelector(`${query}[value="${CUR_Y_AXIS}"]`).classList.add("selected");
}
updateRadios();

function separatedNumber(x) {
    return Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

const ctx = document.getElementById('chart').getContext('2d');
let chart;

const freq_ctx = document.getElementById('freq-chart').getContext('2d');
let freq_chart;

function updateChart() {
  const x_axis = xValues[CUR_X_AXIS].key;
  const y_axis = yValues[CUR_Y_AXIS];
  const logarithmic = ["qdepth", "iosize"].includes(x_axis);
  let iopsData = [];
  let filtered_results = results;

  environments.forEach(({key}) => {
    const selectedRadio = document.querySelector(`input[name="${key}"]:checked`).value;
    if (selectedRadio === 0) {
      filtered_results = filtered_results.map(elem => ({...elem, data: data.filter(d => d[key] === false)}));
    } else if (selectedRadio === 1) {
      filtered_results = filtered_results.map(elem => ({...elem, data: data.filter(d => d[key] === true)}));
    }
  });
  filtered_results = filtered_results.filter(({data}) => data.length);

  for (let result of filtered_results) {
    let filtered = result.data;

    xValues.forEach(({elemId, set, key}, i) => {
      if (i === CUR_X_AXIS) return;
      selectedRadio = document.querySelector(`input[name="${key}"]:checked`).value;
      if (selectedRadio === "undefined") return;
      filtered = filtered.filter(d => d[key] == selectedRadio);
    });

    filtered = filtered.sort((a,b) => a[x_axis] - b[x_axis]);

    const graphData = filtered.map(d => ({
      x: logarithmic ? Math.log2(d[x_axis]) : d[x_axis],
      y: d[y_axis.key][0],
      y_display: d[y_axis.key + '_display'],
      v: d[y_axis.key][1],
      data: d
    }));

    iopsData.push(graphData);
  }

  const maxXvalue = Math.max(...filtered_results[0].data.map(d => d[x_axis])) * (logarithmic ? 2 : 1) + (logarithmic ? 0 : 1);

  const xCategories = BAR_TYPE === 'bar'
    ? [...new Set(iopsData.flat().map(d => d.data[x_axis]))].sort((a,b) => a-b).map(String)
    : null;

  if (xCategories) {
    iopsData = iopsData.map(data => data.map(d => ({...d, x: xCategories.indexOf(String(d.data[x_axis]))})));
  }

  const stacked = typeof STACKED !== 'undefined' && STACKED;

  const datasets = iopsData.map((data, idx) => ({
    data,
    label: filtered_results[idx].label.trim() || `Reached ${y_axis.prettyName}`,
    borderColor: filtered_results[idx].color,
    backgroundColor: filtered_results[idx].color,
    pointStyle: "circle",
    pointRadius: Math.floor(idx*0.2)+3,
    ...(stacked ? { stack: 'stack0' } : {}),
  }));

  if (typeof MAX_LINE_VALUE !== 'undefined' && MAX_LINE_VALUE !== null) {
    const lineLabel = typeof MAX_LINE_LABEL !== 'undefined' ? MAX_LINE_LABEL : 'Max';
    datasets.push({
      type: 'line',
      label: lineLabel,
      data: xCategories
        ? [{x: -0.5, y: MAX_LINE_VALUE}, {x: xCategories.length - 0.5, y: MAX_LINE_VALUE}]
        : [...Array(Math.round(maxXvalue + 2)).keys()].map(x => ({ x: x - 1, y: MAX_LINE_VALUE })),
      clip: false,
      borderColor: 'rgba(0,0,0,0.5)',
      backgroundColor: 'rgba(0,0,0,0)',
      pointRadius: 0,
      borderDash: [10, 5],
      stack: 'line-max',
    });
  }
  if (typeof COMP_LINE_VALUE !== 'undefined' && COMP_LINE_VALUE !== null) {
    const lineLabel = typeof COMP_LINE_LABEL !== 'undefined' ? COMP_LINE_LABEL : 'Max';
    datasets.push({
      type: 'line',
      label: lineLabel,
      data: xCategories
        ? [{x: -0.5, y: COMP_LINE_VALUE}, {x: xCategories.length - 0.5, y: COMP_LINE_VALUE}]
        : [...Array(Math.round(maxXvalue + 2)).keys()].map(x => ({ x: x - 1, y: COMP_LINE_VALUE })),
      clip: false,
      borderColor: 'rgba(0,0,0,0.5)',
      backgroundColor: 'rgba(0,0,0,0)',
      pointRadius: 0,
      borderDash: [10, 5],
      stack: 'line-comp',
    });
  }

  if (y_axis.key === "iops" && BAR_TYPE === 'line') {
    const maxPeak = iopsData.flat().length ? Math.max(...iopsData.flat().map(d => d.data.peakiops)) : 1000;
    datasets.push({
      label: 'Peak IOPS with given devices',
      data: [...Array(Math.round(maxXvalue+2)).keys()].map(x => ({x: x-1, y: maxPeak})),
      borderColor: 'rgba(0,0,0,0.15)',
      backgroundColor: 'white',
      pointRadius: 0,
      borderDash: [10,10]
    });
  }

  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: BAR_TYPE,
    data: {
      datasets: [
        ...datasets,
      ]
    },
    options: {
      animation: false,
      responsive: true,
      scales: {
        x: {
          type: "linear",
          offset: !!xCategories,
          stacked,
          title: { display: true, text: `${xValues[CUR_X_AXIS].prettyName}` },
          min: 0,
          max: xCategories ? xCategories.length - 1 : logarithmic ? Math.log2(maxXvalue) : maxXvalue,
          ticks: {
            stepSize: 1,
            callback: (v) => logarithmic ? Math.pow(2, v) : v,
          },
          grid: { drawTicks: true, tickLength: 10 },
        },
        y: {
          title: { display: true, text: `${y_axis.prettyName} (${y_axis.unit})` },
          stacked,
          min: 0,
          grace: BAR_TYPE === "bar" ? "20%" : 0,
          ticks: { callback: (v) => y_axis.key === "iops" ? v / 1e6 : v },
        }
      },
      onClick: (evt, activeElements) => {
        if (activeElements.length) {
          const datasetIndex = activeElements[0].datasetIndex;
          const index = activeElements[0].index;
          const point = chart.data.datasets[datasetIndex].data[index];
          updateFreqChart(point.data);
          document.querySelector('dialog').show();
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: () => "",
            label: (context) => {
              const d = context.raw;
              const displayY = d.y_display ?? d.y;
              if (context.dataset.label.includes("Peak IOPS")) {
                return `Peak IOPS: ${separatedNumber(d.y)}`;
              } else if (d.data.thr_sib) {
                return [
                  `${y_axis.prettyName}: ${separatedNumber(displayY)} ${y_axis.key ==="iops" ? "" : y_axis.unit}`,
                  `Standard Deviation: ${separatedNumber(d.v)}`,
                  `Hyper threads: ${d.data.hyperthreads}`
                ];
              } else {
                return [
                  `${y_axis.prettyName}: ${separatedNumber(displayY)} ${y_axis.key ==="iops" ? "" : y_axis.unit}`,
                  `Standard Deviation: ${separatedNumber(d.v)}`
                ];
              }
            }
          }
        },
        legend: {
          labels: {
            filter: (legendItem, chartData) => {
              return (chartData.datasets[legendItem.datasetIndex].label);
            }
          }
        },
        errorBars: BAR_TYPE === 'bar' && !stacked,
        shadingArea: BAR_TYPE === 'line',
        showMax: BAR_TYPE === "bar" || document.getElementById("show-max-value").checked,
      },
    }
  });
}

function updateFreqChart(datapoint) {
  const datasets = [];
  let maxXvalue = 0, maxYvalue = 0;

  for (var i = 0; i < datapoint.cpu_freqs.length; i++) {
    let freqs = datapoint.cpu_freqs[i];
    freqs.sort((a,b) => a[1][1] - b[1][1])
    freqs = freqs.map(f => ({x: f[1][1], y: f[0][0], variance: f[0][1], cpu: f[1][0], data: datapoint}));
    const dataset = {
        label: `Run ${i+1}`,
        data: freqs,
        borderColor: colours[i],
        backgroundColor: colours[i],
    }
    datasets.push(dataset);
    maxXvalue = Math.max(maxXvalue, Math.max(...freqs.map(f => f.x)) + 1);
    maxYvalue = Math.max(maxYvalue, Math.max(...freqs.map(f => f.y)) + 1);
  }

  if (freq_chart) freq_chart.destroy();
  freq_chart = new Chart(freq_ctx, {
    type: 'line',
    data: { datasets },
    options: {
      animation: false,
      responsive: true,
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Physical core" },
          offset: true,
          min: 0,
          max: maxXvalue,
          ticks: {
            callback: (v) => v,
          },
          grid: {
            drawTicks: true,
            tickLength: 10
          }
        },
        y: {
          title: { display: true, text: 'CPU frequency (GHz)' },
          offset: true,
          min: 0,
          max: maxYvalue,
          ticks: { callback: (v) => v / 1e6 },
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: () => "",
            label: (context) => {
              const d = context.raw;
              if (d.data.hyperthreads) {
                return [`CPU Frequency: ${Math.round(d.y / 1e2) / 1e4} GHz`,`Hyper thread ID: ${d.cpu}`];
              } else {
                return `CPU Frequency: ${Math.round(d.y / 1e2) / 1e4} GHz`;
              }
            }
          }
        },
        legend: {
          labels: {
            filter: (legendItem, chartData) => {
              return (chartData.datasets[legendItem.datasetIndex].label);
            }
          }
        },
      }
    }
  });
}

document.querySelectorAll(".controls .button-row.x button").forEach(button => {
  button.addEventListener("click", (e) => {
    let selected = Number(button.getAttribute("value"));
    CUR_X_AXIS = selected;
    updateRadios();
    updateChart();
  })
});
document.querySelectorAll(".controls .button-row.y button").forEach(button => {
  button.addEventListener("click", (e) => {
    let selected = Number(button.getAttribute("value"));
    CUR_Y_AXIS = selected;
    updateRadios();
    updateChart();
  })
});

/**
 * Chart plugins
 */
Chart.register({
  id: "shadingArea",
  beforeDatasetsDraw(chart) {
    const { ctx, scales: { y } } = chart;

    const tickHeight = y.height / y.max;
    let count = chart.data.datasets.length;
    if (yValues[CUR_Y_AXIS].key === "iops") count--;

    for (var i = 0; i < count; i++) {
      const dataset = chart.data.datasets[i];
      const dataset_meta = chart.getDatasetMeta(i);
      if (!dataset_meta.data?.length || dataset_meta.hidden) continue;

      ctx.save();

      ctx.beginPath();
      ctx.fillStyle = dataset.backgroundColor;
      ctx.strokeStyle = dataset.backgroundColor;
      ctx.globalAlpha = 0.2;

      ctx.moveTo(dataset_meta.data[0].x, dataset_meta.data[0].y - tickHeight * dataset.data[0].v);

      for (var j = 0; j < dataset.data.length; j++) {
        ctx.lineTo(dataset_meta.data[j].x, dataset_meta.data[j].y - tickHeight * dataset.data[j].v);
      }
      for (var j = dataset.data.length-1; j >= 0; j--) {
        ctx.lineTo(dataset_meta.data[j].x, dataset_meta.data[j].y + tickHeight * dataset.data[j].v);
      }
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
},{
  id: "errorBars",
  afterDatasetsDraw(chart) {
    const { ctx, scales: { y } } = chart;
    let count = chart.data.datasets.length;

    for (var i = 0; i < count; i++) {
      const dataset = chart.data.datasets[i];
      const dataset_meta = chart.getDatasetMeta(i);
      if (!dataset_meta.data?.length || dataset_meta.hidden) continue;

      ctx.save();
      ctx.strokeStyle = "black";
      ctx.lineWidth = 1.5;

      for (var j = 0; j < dataset.data.length; j++) {
        const d = dataset.data[j];
        const bar = dataset_meta.data[j];
        const capHalf = Math.min(bar.width / 4, 6);
        const yTop = y.getPixelForValue(d.y + d.v);
        const yBottom = y.getPixelForValue(Math.max(0, d.y - d.v));

        ctx.beginPath();
        ctx.moveTo(bar.x, yTop);
        ctx.lineTo(bar.x, yBottom);
        ctx.moveTo(bar.x - capHalf, yTop);
        ctx.lineTo(bar.x + capHalf, yTop);
        ctx.moveTo(bar.x - capHalf, yBottom);
        ctx.lineTo(bar.x + capHalf, yBottom);
        ctx.stroke();
      }

      ctx.restore();
    }
  }
},{
  id: "showMax",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const drawn_labels = [];
    const stacked = typeof STACKED !== 'undefined' && STACKED;

    let count = chart.data.datasets.length;
    if (BAR_TYPE === "line" && yValues[CUR_Y_AXIS].key === "iops") count--;

    for (var i = 0; i < count; i++) {
      const dataset = chart.data.datasets[i];
      const dataset_meta = chart.getDatasetMeta(i);
      if (!dataset_meta.data?.length || dataset_meta.hidden) continue;

      ctx.save();
      ctx.fillStyle = dataset.backgroundColor;
      ctx.strokeStyle = dataset.backgroundColor;

      if (BAR_TYPE === "bar") {
        if (dataset.type === 'line') {
          ctx.restore();
          continue;
        }

        ctx.textAlign = stacked ? "center" : "left";

        for (var j = 0; j < dataset.data.length; j++) {
          const bar = dataset_meta.data[j];
          const value = dataset.data[j].y_display ?? dataset.data[j].y;
          const text = value > 1000 ? separatedNumber(value) : value.toFixed(1);

          ctx.save();
          if (stacked) {
            ctx.translate(bar.x, bar.y + 10);
            ctx.fillStyle = "white";
          } else {
            ctx.translate(bar.x, bar.y - 10);
            ctx.rotate(-Math.PI / 2);
            ctx.fillStyle = "black";
          }
          ctx.fillText(text, 0, 0);
          ctx.restore();

        }
      } else {
        const lastPoint = dataset.data[dataset.data.length-1];
        const lastPointMeta = dataset_meta.data[dataset.data.length-1];
        const text = separatedNumber(lastPoint.y);

        const coord = { x: lastPointMeta.x + 10, y: lastPointMeta.y-6, w: ctx.measureText(text).width, h: 10 };

        let goUp = coord.y;
        let goDown = coord.y;

        while (drawn_labels.some(r =>
          goDown < r.y + r.h &&
          goDown + coord.h > r.y
        )) {
          goDown += 4;
        }
        while (drawn_labels.some(r =>
          goUp < r.y + r.h &&
          goUp + coord.h > r.y
        )) {
          goUp -= 4;
        }

        if (coord.y-goUp < goDown-coord.y) coord.y = goUp;
        else coord.y = goDown;

        ctx.fillText(text, coord.x, coord.y+6);
        drawn_labels.push({ ...coord, y: coord.y });
      }
    }
  }
});
updateChart();

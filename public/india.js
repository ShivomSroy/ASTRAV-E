(function () {
  'use strict';

  var eventRecords = [];
  var currentEvent = null;
  var currentResult = null;
  var resultLoaded = false;
  var requestVersion = 0;
  var mapConfig = null;
  var mapConfigReady = false;
  var mapInstance = null;
  var tileLayer = null;
  var boundsLayer = null;
  var zoomControl = null;
  var tileErrorCount = 0;
  var basemapUnavailable = false;

  if (!window.IndiaStrings) {
    console.error('India page translations could not be loaded.');
    return;
  }

  function strings() {
    return window.IndiaStrings.en;
  }

  function setText(element, value) {
    if (!element) return;
    element.textContent = value == null ? '' : String(value);
    element.setAttribute('lang', 'en');
  }

  function makeElement(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) setText(element, text);
    return element;
  }

  function appendNote(container, text) {
    if (!container || !text) return;
    var note = makeElement('p', 'img-label', text);
    container.hidden = false;
    container.appendChild(note);
  }

  function clear(element) {
    if (element) element.textContent = '';
  }

  function isSensitiveUrl(url) {
    var sensitive = false;
    url.searchParams.forEach(function (_value, key) {
      if (/token|user|pass/i.test(key)) sensitive = true;
    });
    return sensitive;
  }

  function safeServiceUrl(value, host) {
    if (typeof value !== 'string' || !value) return '';
    try {
      var url = new URL(value);
      if (url.protocol !== 'https:' || url.hostname.toLowerCase() !== host ||
          url.username || url.password || isSensitiveUrl(url)) {
        return '';
      }
      url.hash = '';
      return url.href;
    } catch (error) {
      return '';
    }
  }

  function safeSourceUrl(value) {
    if (typeof value !== 'string' || !value) return '';
    try {
      var url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password || isSensitiveUrl(url)) {
        return '';
      }
      url.hash = '';
      return url.href;
    } catch (error) {
      return '';
    }
  }

  function safeLocalImagePath(value) {
    if (typeof value !== 'string' || !value.trim()) return '';
    try {
      var url = new URL(value, window.location.href);
      if (url.origin !== window.location.origin || url.username || url.password) return '';
      return url.href;
    } catch (error) {
      return '';
    }
  }

  function readJson(path) {
    return fetch(path).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status + ' for ' + path);
      return response.json();
    });
  }

  function eventDate(record) {
    return record.event_date_text || '';
  }

  function renderEventHeader() {
    if (!currentEvent) return;
    var text = strings();
    var name = (text.events && text.events[currentEvent.id]) || currentEvent.id;
    var date = eventDate(currentEvent);
    setText(document.getElementById('event-heading'), name);
    setText(document.getElementById('event-date'), text.eventDateLabel + ': ' + date);
    setText(document.getElementById('event-date-label'), text.eventDateLabel);
    setText(document.getElementById('hypothesis-date'), date);
    setText(document.getElementById('hypothesis-text'),
      text.hypotheses && text.hypotheses[currentEvent.id] || '');

    var verification = document.getElementById('event-verify');
    if (verification) {
      verification.hidden = !currentEvent.verify;
      setText(verification, text.verifyNote);
    }
  }

  function updateStaticText() {
    var text = strings();
    setText(document.getElementById('page-title'), text.pageTitle);
    setText(document.getElementById('page-intro'), text.intro);
    setText(document.getElementById('problem-heading'), text.problemHeading);
    setText(document.getElementById('problem-text'), text.problem);
    setText(document.getElementById('audience-purpose'), text.audiencePurpose);
    setText(document.getElementById('event-selector-heading'), text.eventSelector);
    setText(document.getElementById('map-heading'), text.mapHeading);
    setText(document.getElementById('map-disclaimer'), text.mapDisclaimer);
    setText(document.getElementById('status-heading'), text.dataStatusHeading);
    setText(document.getElementById('coverage-heading'), text.coverageHeading);
    setText(document.getElementById('rainfall-heading'), text.rainfallHeading);
    setText(document.getElementById('rain-caption'), text.rainfallCaption);
    setText(document.getElementById('eonet-heading'), text.naturalEventsHeading);
    setText(document.getElementById('hypothesis-heading'), text.whatSeeingHeading);
    setText(document.getElementById('limitations-heading'), text.limitationsHeading);
    setText(document.getElementById('api-requests-heading'), text.apiRequestsHeading);
    setText(document.getElementById('api-metadata-note'), text.apiMetadataNote);
    setText(document.getElementById('india-footer'), text.footer);

    var eventTabs = document.getElementById('india-event-tabs');
    if (eventTabs) eventTabs.setAttribute('aria-label', text.eventSelector);
    var layerSection = document.getElementById('layer-section');
    if (layerSection) layerSection.setAttribute('aria-label', text.layerSectionLabel);
    var map = document.getElementById('map');
    if (map) map.setAttribute('aria-label', text.mapAriaLabel);
    var compareRange = document.getElementById('india-compare-range');
    if (compareRange) compareRange.setAttribute('aria-label', text.compareRangeLabel);

    document.querySelectorAll('[data-event]').forEach(function (button) {
      setText(button, text.events[button.dataset.event] || button.dataset.event);
      button.setAttribute('aria-pressed', String(currentEvent && button.dataset.event === currentEvent.id));
    });

    if (currentEvent) {
      renderEventHeader();
      renderLayers(currentEvent);
      updateMap(currentEvent);
    }
    if (basemapUnavailable) setBasemapNote(true);
    if (mapInstance && zoomControl) updateZoomControlText();
    if (currentEvent && resultLoaded) renderResult(currentResult);
  }

  function updateZoomControlText() {
    if (!zoomControl) return;
    var text = strings();
    var zoomIn = zoomControl.getContainer().querySelector('.leaflet-control-zoom-in');
    var zoomOut = zoomControl.getContainer().querySelector('.leaflet-control-zoom-out');
    if (zoomIn) {
      zoomIn.title = text.mapZoomIn;
      zoomIn.setAttribute('aria-label', text.mapZoomIn);
    }
    if (zoomOut) {
      zoomOut.title = text.mapZoomOut;
      zoomOut.setAttribute('aria-label', text.mapZoomOut);
    }
  }

  function setBasemapNote(unavailable) {
    basemapUnavailable = unavailable;
    var note = document.getElementById('map-offline-note');
    if (!note) return;
    note.hidden = !unavailable;
    setText(note, strings().basemapUnavailable);
  }

  function getAccentColor() {
    return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  }

  function addBaseLayer() {
    if (!mapInstance || !mapConfigReady || !mapConfig || tileLayer || !window.L) {
      if (mapConfigReady && (!mapConfig || !mapConfig.layer || !mapConfig.matrixSet || !mapConfig.date)) {
        setBasemapNote(true);
      }
      return;
    }

    var tileUrl = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/' +
      encodeURIComponent(mapConfig.layer) + '/default/' + encodeURIComponent(mapConfig.date) + '/' +
      encodeURIComponent(mapConfig.matrixSet) + '/{z}/{y}/{x}.jpg';
    tileErrorCount = 0;
    tileLayer = L.tileLayer(tileUrl, {
      maxNativeZoom: 9,
      maxZoom: 18,
      attribution: strings().mapAttribution
    });
    tileLayer.on('tileerror', function () {
      tileErrorCount += 1;
      setBasemapNote(true);
    });
    tileLayer.on('tileload', function () {
      if (!tileErrorCount) setBasemapNote(false);
    });
    tileLayer.addTo(mapInstance);
  }

  function updateMap(record) {
    if (!record) return;
    var mapElement = document.getElementById('map');
    if (!mapElement) return;
    if (!window.L) {
      setBasemapNote(true);
      return;
    }

    if (!mapInstance) {
      mapInstance = L.map(mapElement, { scrollWheelZoom: false, zoomControl: false });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(mapInstance);
      zoomControl = L.control.zoom({
        zoomInTitle: strings().mapZoomIn,
        zoomOutTitle: strings().mapZoomOut
      }).addTo(mapInstance);
      updateZoomControlText();
    }
    addBaseLayer();

    var bbox = (record.bbox || '').split(',').map(Number);
    if (bbox.length !== 4 || bbox.some(function (value) { return !isFinite(value); })) return;

    if (boundsLayer) mapInstance.removeLayer(boundsLayer);
    var west = bbox[0];
    var south = bbox[1];
    var east = bbox[2];
    var north = bbox[3];
    var bounds = [[south, west], [north, east]];
    boundsLayer = L.rectangle(bounds, {
      color: getAccentColor(),
      weight: 3,
      fillOpacity: 0
    }).addTo(mapInstance);

    var popup = document.createElement('div');
    var popupTitle = makeElement('strong', '', (strings().events[record.id] || record.id));
    var popupCoordinates = makeElement('p', '', record.bbox);
    popup.appendChild(popupTitle);
    popup.appendChild(popupCoordinates);
    boundsLayer.bindPopup(popup);

    mapInstance.fitBounds(bounds, { padding: [32, 32], maxZoom: 8 });
    window.setTimeout(function () { if (mapInstance) mapInstance.invalidateSize(); }, 100);
  }

  function appendBadge(container, text) {
    var badge = makeElement('span', 'chip', text);
    container.appendChild(badge);
  }

  function entryId(entry) {
    if (!entry || typeof entry !== 'object') return '';
    return entry.granule_ur || entry.producer_granule_id ||
      entry.umm && entry.umm.GranuleUR || '';
  }

  function entryDate(entry) {
    var temporal = entry && entry.umm && entry.umm.TemporalExtent;
    var range = temporal && temporal.RangeDateTime;
    return entry && (entry.time_start || entry.start_date) ||
      range && range.BeginningDateTime ||
      temporal && temporal.SingleDateTime || '';
  }

  function renderCoverage(result) {
    var list = document.getElementById('granule-list');
    var empty = document.getElementById('coverage-empty');
    if (!list || !empty) return;
    clear(list);
    empty.hidden = true;

    var cmr = result && result.cmr;
    if (!cmr) {
      empty.hidden = false;
      setText(empty, strings().noSavedResults);
      return;
    }
    var entries = Array.isArray(cmr.entries) ? cmr.entries.slice(0, 10) : [];
    if (!entries.length) {
      empty.hidden = false;
      setText(empty, strings().noGranulesListed);
      return;
    }

    entries.forEach(function (entry) {
      if (!entry || typeof entry !== 'object') return;
      var item = document.createElement('li');
      var id = entryId(entry);
      var date = entryDate(entry);

      if (id) {
        var idLine = makeElement('p', '', strings().granuleIdLabel + ': ' + id);
        item.appendChild(idLine);
      }
      if (date) {
        var dateLine = makeElement('p', '', strings().startDateLabel + ': ' + date);
        item.appendChild(dateLine);
      }
      if (entry.id && window.AstraveCmr) {
        var metadataUrl = window.AstraveCmr.safeCmrUrl(
          window.AstraveCmr.conceptMetadataUrl(entry)
        );
        if (metadataUrl) {
          var link = makeElement('a', 'india-api-link', strings().metadataLink);
          link.href = metadataUrl;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          item.appendChild(link);
        }
      }
      if (item.childElementCount) list.appendChild(item);
    });

    if (!list.childElementCount) {
      empty.hidden = false;
      setText(empty, strings().noGranulesListed);
    }
  }

  function setLayerImage(imageId, layer) {
    var image = document.getElementById(imageId);
    var path = safeLocalImagePath(layer && layer.path);
    if (!image || !path) return false;
    image.src = path;
    image.alt = layer.label || strings().layerNisar;
    image.setAttribute('lang', 'en');
    return true;
  }

  function renderLayerDetails(layers) {
    var list = document.getElementById('india-layer-details');
    if (!list) return;
    clear(list);
    layers.forEach(function (layer) {
      if (!layer || typeof layer !== 'object') return;
      var item = document.createElement('li');
      var parts = [];
      if (layer.label) parts.push(layer.label);
      if (layer.date) parts.push(strings().layerDateLabel + ': ' + layer.date);
      var typeText = layer.data_type === 'analogue' ? strings().layerAnalogue :
        layer.data_type === 'nisar' ? strings().layerNisar : layer.data_type;
      if (typeText) parts.push(typeText);
      if (parts.length) item.appendChild(makeElement('span', '', parts.join(' · ')));

      if (layer.path) {
        var path = safeLocalImagePath(layer.path);
        item.appendChild(makeElement('span', '', ' · ' + strings().layerPathLabel + ': '));
        if (path) {
          var pathLink = makeElement('a', 'india-api-link', layer.path);
          pathLink.href = path;
          pathLink.target = '_blank';
          pathLink.rel = 'noopener noreferrer';
          item.appendChild(pathLink);
        } else {
          item.appendChild(makeElement('span', '', layer.path));
        }
      }
      if (layer.source) {
        item.appendChild(makeElement('span', '', ' · ' + strings().layerSourceLabel + ': '));
        var sourceUrl = safeSourceUrl(layer.source);
        if (sourceUrl) {
          var sourceLink = makeElement('a', 'india-api-link', layer.source);
          sourceLink.href = sourceUrl;
          sourceLink.target = '_blank';
          sourceLink.rel = 'noopener noreferrer';
          item.appendChild(sourceLink);
        } else {
          item.appendChild(makeElement('span', '', layer.source));
        }
      }
      list.appendChild(item);
    });
  }

  function renderLayers(record) {
    var section = document.getElementById('layer-section');
    if (!section) return;
    var compareBlock = document.getElementById('india-compare-block');
    var layers = Array.isArray(record.layers) ? record.layers.filter(function (layer) {
      return layer && typeof layer === 'object';
    }) : [];
    section.hidden = !layers.length;
    if (!layers.length) return;

    var imageLayers = layers.filter(function (layer) {
      return !!safeLocalImagePath(layer.path);
    });
    compareBlock.hidden = !imageLayers.length;
    renderLayerDetails(layers);
    if (!imageLayers.length) return;

    var beforeTag = document.getElementById('india-before-tag');
    var afterTag = document.getElementById('india-after-tag');
    var afterWrap = document.getElementById('india-layer-after-wrap');
    var range = document.getElementById('india-compare-range');
    var handle = document.querySelector('#india-compare .handle');
    var before = imageLayers[0];
    setLayerImage('india-layer-before', before);
    setText(beforeTag, before.label || strings().layerNisar);

    if (imageLayers.length > 1) {
      setLayerImage('india-layer-after', imageLayers[1]);
      afterWrap.hidden = false;
      afterTag.hidden = false;
      handle.hidden = false;
      range.hidden = false;
      setText(beforeTag, strings().before);
      setText(afterTag, strings().after);
      document.getElementById('india-compare').style.setProperty('--pos', range.value + '%');
    } else {
      afterWrap.hidden = true;
      afterTag.hidden = true;
      handle.hidden = true;
      range.hidden = true;
      document.getElementById('india-compare').style.setProperty('--pos', '100%');
    }
  }

  function renderRainfall(record, result) {
    var section = document.getElementById('rainfall-section');
    if (!section) return;
    var chart = document.getElementById('rain-chart');
    var empty = document.getElementById('rain-empty');
    var caption = document.getElementById('rain-caption');
    var values = result && result.power && result.power.data;
    section.hidden = !(record.rain && values && typeof values === 'object');
    if (section.hidden) return;

    chart.textContent = '';
    empty.hidden = true;
    caption.hidden = true;
    var points = Object.keys(values).sort().map(function (date) {
      var value = Number(values[date]);
      return { date: date, value: value };
    }).filter(function (point) {
      return isFinite(point.value) && point.value !== -999;
    });

    if (!points.length) {
      empty.hidden = false;
      setText(empty, strings().noRainfallData);
      return;
    }

    caption.hidden = false;
    var svgNamespace = 'http://www.w3.org/2000/svg';
    var width = 720;
    var height = 200;
    var left = 12;
    var right = 8;
    var top = 10;
    var bottom = 10;
    var plotWidth = width - left - right;
    var plotHeight = height - top - bottom;
    var minimum = Math.min.apply(null, points.map(function (point) { return point.value; }).concat([0]));
    var maximum = Math.max.apply(null, points.map(function (point) { return point.value; }).concat([0]));
    var span = maximum - minimum || 1;
    var baseline = top + maximum / span * plotHeight;
    var barStep = plotWidth / points.length;
    var barWidth = Math.max(1, barStep * 0.72);
    var baselineLine = document.createElementNS(svgNamespace, 'line');
    baselineLine.setAttribute('x1', left);
    baselineLine.setAttribute('x2', width - right);
    baselineLine.setAttribute('y1', baseline);
    baselineLine.setAttribute('y2', baseline);
    baselineLine.setAttribute('stroke', 'var(--line)');
    chart.appendChild(baselineLine);

    points.forEach(function (point, index) {
      var barHeight = Math.abs(point.value) / span * plotHeight;
      var rect = document.createElementNS(svgNamespace, 'rect');
      rect.setAttribute('x', left + index * barStep + (barStep - barWidth) / 2);
      rect.setAttribute('y', point.value >= 0 ? baseline - barHeight : baseline);
      rect.setAttribute('width', barWidth);
      rect.setAttribute('height', barHeight);
      rect.setAttribute('fill', 'var(--accent)');
      var title = document.createElementNS(svgNamespace, 'title');
      title.textContent = point.date + ': ' + point.value;
      rect.appendChild(title);
      chart.appendChild(rect);
    });
    chart.setAttribute('aria-label', strings().rainfallCaption);
    chart.setAttribute('lang', 'en');
  }

  function renderEonet(result) {
    var list = document.getElementById('eonet-list');
    var empty = document.getElementById('eonet-empty');
    if (!list || !empty) return;
    clear(list);
    empty.hidden = true;
    var eonet = result && result.eonet;
    if (!eonet || !Array.isArray(eonet.events)) {
      empty.hidden = false;
      setText(empty, strings().showingSavedData);
      return;
    }
    if (!eonet.events.length) {
      empty.hidden = false;
      setText(empty, strings().noEonetEvents);
      return;
    }

    eonet.events.forEach(function (event) {
      if (!event || typeof event !== 'object') return;
      var item = document.createElement('li');
      var title = makeElement('strong', '', event.title || '');
      item.appendChild(title);
      var category = Array.isArray(event.categories) && event.categories.length
        ? event.categories[0].title : '';
      if (category) item.appendChild(makeElement('span', '', ' · ' + category));
      var geometry = Array.isArray(event.geometry) && event.geometry.length
        ? event.geometry[event.geometry.length - 1] : null;
      var date = geometry && geometry.date || event.closed || '';
      if (date) item.appendChild(makeElement('span', '', ' · ' + date));

      var source = Array.isArray(event.sources) && event.sources.length
        ? event.sources[0] : null;
      var sourceUrl = source && safeSourceUrl(source.url || source.source || source.link);
      if (sourceUrl) {
        item.appendChild(makeElement('span', '', ' · ' + strings().eventSourceLabel + ': '));
        var link = makeElement('a', 'india-api-link', source.title || source.id || sourceUrl);
        link.href = sourceUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        item.appendChild(link);
      }
      list.appendChild(item);
    });
  }

  function requestUrl(result, key) {
    if (!result || !result[key] || typeof result[key] !== 'object') return '';
    return result[key].request_url || '';
  }

  function appendRequestLink(container, label, url, host, isCmr) {
    var safeUrl = isCmr
      ? window.AstraveCmr && window.AstraveCmr.safeCmrUrl(url)
      : safeServiceUrl(url, host);
    if (!safeUrl) return false;

    var line = makeElement('p', 'img-label', label + ': ');
    var link = makeElement('a', 'india-api-link', safeUrl);
    link.href = safeUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    line.appendChild(link);
    container.appendChild(line);
    return true;
  }

  function renderApiRequests(result) {
    var section = document.getElementById('api-requests-section');
    var container = document.getElementById('api-requests-list');
    var metadataNote = document.getElementById('api-metadata-note');
    if (!section || !container || !metadataNote) return;
    clear(container);
    var text = strings();
    var count = 0;
    if (appendRequestLink(container, text.apiCmrLabel, requestUrl(result, 'cmr'),
        'cmr.earthdata.nasa.gov', true)) count += 1;
    if (appendRequestLink(container, text.apiEonetLabel, requestUrl(result, 'eonet'),
        'eonet.gsfc.nasa.gov', false)) count += 1;
    if (appendRequestLink(container, text.apiPowerLabel, requestUrl(result, 'power'),
        'power.larc.nasa.gov', false)) count += 1;
    section.hidden = count === 0;
    metadataNote.hidden = count === 0;
  }

  function renderResult(result) {
    var text = strings();
    var badges = document.getElementById('data-status-badges');
    if (!badges) return;
    var note = document.getElementById('data-status-note');
    var analogueNote = document.getElementById('analogue-source-note');
    clear(badges);
    clear(note);
    clear(analogueNote);
    note.hidden = true;
    analogueNote.hidden = true;

    var layers = currentEvent && Array.isArray(currentEvent.layers) ? currentEvent.layers : [];
    var isAnalogue = currentEvent && currentEvent.data_type === 'analogue' ||
      layers.some(function (layer) { return layer && layer.data_type === 'analogue'; });
    var cmr = result && result.cmr;
    var hasCmr = !!cmr && typeof cmr === 'object';
    var hits = hasCmr && cmr.hits !== null && cmr.hits !== undefined
      ? Number(cmr.hits) : NaN;

    if (isFinite(hits) && hits > 0) {
      appendBadge(badges, text.statusNisarFound + ' (' + hits + ')');
      appendNote(note, text.metadataOnly);
    } else if (hasCmr && isFinite(hits) && hits === 0) {
      appendBadge(badges, text.statusNoNisar);
    } else {
      appendNote(note, text.noSavedResults);
    }
    if (isAnalogue) appendBadge(badges, text.statusAnalogue);
    if (hasCmr) appendNote(note, text.searchWindowNote);

    if (isAnalogue) {
      if (currentEvent.analogue_source) {
        analogueNote.hidden = false;
        setText(analogueNote, text.layerSourceLabel + ': ' + currentEvent.analogue_source);
      } else if (!layers.length) {
        analogueNote.hidden = false;
        setText(analogueNote, text.analogueSourceMissing);
      }
    }

    renderCoverage(result);
    renderRainfall(currentEvent, result);
    renderEonet(result);
    renderApiRequests(result);
  }

  function loadEventResult(record) {
    var version = ++requestVersion;
    currentEvent = record;
    currentResult = null;
    resultLoaded = false;
    var content = document.getElementById('event-content');
    var unavailable = document.getElementById('event-unavailable');
    if (content) content.hidden = false;
    if (unavailable) unavailable.hidden = true;
    renderEventHeader();
    renderLayers(record);
    renderResult(null);
    updateMap(record);

    readJson('data/india/' + encodeURIComponent(record.id) + '.json')
      .then(function (result) {
        if (version !== requestVersion) return;
        currentResult = result;
        resultLoaded = true;
        renderResult(result);
      })
      .catch(function (error) {
        if (version !== requestVersion) return;
        console.warn('Saved India event data is unavailable for ' + record.id + ':', error);
        currentResult = null;
        resultLoaded = true;
        renderResult(null);
      });
  }

  function syncPageLinks(eventId) {
    var dataLink = document.querySelector('a[href="data.html"], a[href^="data.html#"]');
    var indiaLink = document.querySelector('a[href="india.html"], a[href^="india.html#"]');
    if (dataLink) dataLink.href = 'data.html#' + eventId;
    if (indiaLink) indiaLink.href = 'india.html#' + eventId;
  }

  function selectEvent(eventId) {
    syncPageLinks(eventId);
    document.querySelectorAll('[data-event]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.event === eventId));
    });
    var record = eventRecords.find(function (item) { return item.id === eventId; });
    if (!record) {
      currentEvent = null;
      var content = document.getElementById('event-content');
      if (content) content.hidden = true;
      var unavailable = document.getElementById('event-unavailable');
      if (unavailable) {
        unavailable.hidden = false;
        setText(unavailable, strings().noSavedResults);
      }
      return;
    }
    loadEventResult(record);
  }

  function handleHash() {
    var eventId = window.location.hash.replace('#', '').toLowerCase();
    var valid = eventRecords.some(function (record) { return record.id === eventId; });
    selectEvent(valid ? eventId : 'assam_flood');
  }

  function drawInitialContent() {
    document.querySelectorAll('[data-event]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (window.location.hash !== '#' + button.dataset.event) {
          history.replaceState(null, '', '#' + button.dataset.event);
        }
        selectEvent(button.dataset.event);
      });
    });

    var compareRange = document.getElementById('india-compare-range');
    if (compareRange) {
      compareRange.addEventListener('input', function () {
        document.getElementById('india-compare').style.setProperty('--pos', this.value + '%');
      });
    }

    var themeButton = document.getElementById('theme-toggle');
    if (themeButton) {
      themeButton.addEventListener('click', function () {
        window.setTimeout(function () {
          if (boundsLayer) boundsLayer.setStyle({ color: getAccentColor() });
        }, 0);
      });
    }

    window.addEventListener('hashchange', handleHash);
    updateStaticText();

    if (document.getElementById('map')) {
      readJson('data/india/map-config.json')
        .then(function (config) {
          mapConfig = config;
          mapConfigReady = true;
          if (currentEvent) updateMap(currentEvent);
        })
        .catch(function (error) {
          console.warn('India map configuration is unavailable:', error);
          mapConfigReady = true;
          setBasemapNote(true);
        });
    }

    readJson('data/india/events.json')
      .then(function (data) {
        eventRecords = data && Array.isArray(data.events) ? data.events : [];
        handleHash();
      })
      .catch(function (error) {
        console.warn('India event records are unavailable:', error);
        eventRecords = [];
        handleHash();
      });
  }

  drawInitialContent();
})();

(function (global) {
  var savedSearchPromise;

  function text(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function load() {
    if (!savedSearchPromise) {
      savedSearchPromise = fetch('data/granule_search.json')
        .then(function (response) {
          if (response.status === 404) return null;
          if (!response.ok) throw new Error('HTTP ' + response.status);
          return response.text();
        })
        .then(function (body) {
          if (body === null || !body.trim()) return null;
          var data = JSON.parse(body);
          if (!data || typeof data !== 'object' || Array.isArray(data) || !Object.keys(data).length) {
            return null;
          }
          return data;
        });
    }
    return savedSearchPromise;
  }

  function entries(search) {
    return search && Array.isArray(search.entries) ? search.entries : [];
  }

  function conceptId(entry) {
    return text(entry && (entry.id || entry.concept_id));
  }

  function granuleId(entry) {
    var umm = entry && entry.umm;
    return text(entry && (entry.granule_ur || entry.producer_granule_id)) ||
      text(umm && umm.GranuleUR) ||
      conceptId(entry);
  }

  function startDate(entry) {
    var umm = entry && entry.umm;
    var temporal = umm && umm.TemporalExtent;
    var range = temporal && temporal.RangeDateTime;
    return text(entry && (entry.time_start || entry.start_date)) ||
      text(range && range.BeginningDateTime) ||
      text(temporal && temporal.SingleDateTime);
  }

  function collectionName(search, entry) {
    var umm = entry && entry.umm;
    var reference = umm && (umm.CollectionReference || umm.collection_reference);
    var referenceLower = entry && entry.collection_reference;
    return text(search && (search.collection_name || search.collection_short_name)) ||
      text(entry && (entry.collection_name || entry.collection_short_name || entry.dataset_id)) ||
      text(reference && (reference.ShortName || reference.Title || reference.short_name)) ||
      text(referenceLower && (referenceLower.short_name || referenceLower.title));
  }

  function collectionId(search, entry) {
    return text(search && (search.collection || search.collection_id)) ||
      text(entry && entry.collection_concept_id);
  }

  function matchingEntries(search, date, eventId) {
    var day = text(date).slice(0, 10);
    if (!day) return [];
    var searchEntries = entries(search);
    if (eventId && search && Array.isArray(search.searches)) {
      var eventSearch = search.searches.find(function (item) {
        return item && item.event_id === eventId;
      });
      searchEntries = entries(eventSearch);
    }
    return searchEntries.filter(function (entry) {
      return startDate(entry).slice(0, 10) === day;
    });
  }

  function hasSensitiveQuery(url) {
    var sensitive = false;
    url.searchParams.forEach(function (_value, key) {
      if (/token|user|pass/i.test(key)) sensitive = true;
    });
    return sensitive;
  }

  function safeCmrUrl(value) {
    if (typeof value !== 'string' || !value) return '';
    try {
      var url = new URL(value);
      var isSearchPath = url.pathname === '/search' || url.pathname.startsWith('/search/');
      if (url.protocol !== 'https:' ||
          url.hostname.toLowerCase() !== 'cmr.earthdata.nasa.gov' ||
          url.username || url.password || !isSearchPath ||
          hasSensitiveQuery(url)) {
        return '';
      }
      url.hash = '';
      return url.href;
    } catch (error) {
      return '';
    }
  }

  function safeDocumentationUrl(value) {
    if (typeof value !== 'string' || !value) return '';
    try {
      var url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password || hasSensitiveQuery(url)) {
        return '';
      }
      url.hash = '';
      return url.href;
    } catch (error) {
      return '';
    }
  }

  function conceptMetadataUrl(entry) {
    var id = conceptId(entry);
    if (!/^[A-Za-z0-9._-]+$/.test(id)) return '';
    return 'https://cmr.earthdata.nasa.gov/search/concepts/' +
      encodeURIComponent(id) + '.umm_json';
  }

  global.AstraveCmr = {
    load: load,
    entries: entries,
    conceptId: conceptId,
    granuleId: granuleId,
    startDate: startDate,
    collectionName: collectionName,
    collectionId: collectionId,
    matchingEntries: matchingEntries,
    safeCmrUrl: safeCmrUrl,
    safeDocumentationUrl: safeDocumentationUrl,
    conceptMetadataUrl: conceptMetadataUrl
  };
})(window);

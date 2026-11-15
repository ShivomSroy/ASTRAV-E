const fs = require('fs');
const path = require('path');

exports.handler = async (event, context) => {
  const pathParts = event.path
    .replace(/^\/\.netlify\/functions\/api/, '')
    .replace(/^\/api/, '')
    .split('/')
    .filter(Boolean);

  const route = pathParts[0];
  const subRoute = pathParts[1];

  function readData(file) {
    const candidates = [
      path.join(__dirname, '..', '..', 'data', file),
      path.join(process.cwd(), 'data', file),
      path.join(__dirname, 'data', file)
    ];
    for (const p of candidates) {
      try {
        if (fs.existsSync(p)) {
          return JSON.parse(fs.readFileSync(p, 'utf8'));
        }
      } catch (err) {
        // continue
      }
    }
    return null;
  }

  const jsonHeaders = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*'
  };

  if (route === 'events') {
    const events = readData('events.json');
    if (!events) {
      return { statusCode: 500, headers: jsonHeaders, body: JSON.stringify({ error: 'Failed to load events data' }) };
    }
    if (subRoute) {
      const item = events.find(e => e.id.toLowerCase() === subRoute.toLowerCase());
      if (!item) {
        return { statusCode: 404, headers: jsonHeaders, body: JSON.stringify({ error: `Event '${subRoute}' not found` }) };
      }
      return { statusCode: 200, headers: jsonHeaders, body: JSON.stringify(item) };
    }
    const summaryList = events.map(e => ({
      id: e.id,
      title: e.title,
      type: e.type,
      thumb: e.thumb,
      summary: e.summary
    }));
    return { statusCode: 200, headers: jsonHeaders, body: JSON.stringify(summaryList) };
  }

  if (route === 'sources') {
    const sources = readData('sources.json');
    return { statusCode: 200, headers: jsonHeaders, body: JSON.stringify(sources || []) };
  }

  if (route === 'team') {
    const team = readData('team.json');
    return { statusCode: 200, headers: jsonHeaders, body: JSON.stringify(team || []) };
  }

  if (route === 'steps') {
    const steps = readData('steps.json');
    return { statusCode: 200, headers: jsonHeaders, body: JSON.stringify(steps || []) };
  }

  return {
    statusCode: 404,
    headers: jsonHeaders,
    body: JSON.stringify({ error: 'API route not found' })
  };
};

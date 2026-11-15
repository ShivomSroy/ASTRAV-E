const express = require('express');
const fs = require('fs');
const path = require('path');
const http = require('http');

const app = express();
const DEFAULT_PORT = parseInt(process.env.PORT, 10) || 3000;

// Serve static frontend files
app.use(express.static(path.join(__dirname, 'public')));
app.use('/src', express.static(path.join(__dirname, 'src')));

// Helpers to read JSON data
function readDataFile(filename) {
  const filepath = path.join(__dirname, 'data', filename);
  try {
    const raw = fs.readFileSync(filepath, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    console.error(`Error reading ${filename}:`, err);
    return null;
  }
}

// -------------------------------------------------------------
// API Routes
// -------------------------------------------------------------

// GET /api/events -> list of {id, title, type, thumb, summary}
app.get('/api/events', (req, res) => {
  const events = readDataFile('events.json');
  if (!events) {
    return res.status(500).json({ error: 'Failed to load events data' });
  }
  const summaryList = events.map(e => ({
    id: e.id,
    title: e.title,
    type: e.type,
    thumb: e.thumb,
    summary: e.summary
  }));
  res.json(summaryList);
});

// GET /api/events/:id -> detailed event data
app.get('/api/events/:id', (req, res) => {
  const events = readDataFile('events.json');
  if (!events) {
    return res.status(500).json({ error: 'Failed to load events data' });
  }
  const targetId = req.params.id.toLowerCase();
  const event = events.find(e => e.id.toLowerCase() === targetId);
  if (!event) {
    return res.status(404).json({ error: `Event '${req.params.id}' not found` });
  }
  res.json(event);
});

// GET /api/sources -> rows for the Data sources table
app.get('/api/sources', (req, res) => {
  const sources = readDataFile('sources.json');
  if (!sources) {
    return res.status(500).json({ error: 'Failed to load sources data' });
  }
  res.json(sources);
});

// GET /api/team -> 6 team members {role, name}
app.get('/api/team', (req, res) => {
  const team = readDataFile('team.json');
  if (!team) {
    return res.status(500).json({ error: 'Failed to load team data' });
  }
  res.json(team);
});

// GET /api/steps -> the 4 "How SAR works" steps
app.get('/api/steps', (req, res) => {
  const steps = readDataFile('steps.json');
  if (!steps) {
    return res.status(500).json({ error: 'Failed to load steps data' });
  }
  res.json(steps);
});

// -------------------------------------------------------------
// Start server on free port
// -------------------------------------------------------------
function startServer(port) {
  const server = http.createServer(app);

  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`Port ${port} is in use, trying port ${port + 1}...`);
      startServer(port + 1);
    } else {
      console.error('Server error:', err);
    }
  });

  server.listen(port, '0.0.0.0', () => {
    console.log(`Astrave server running on port ${port}`);
    console.log(`Explore pages:`);
    console.log(`  - Home:        http://localhost:${port}/index.html`);
    console.log(`  - Viewer:      http://localhost:${port}/viewer.html`);
    console.log(`  - How SAR:     http://localhost:${port}/how-sar.html`);
    console.log(`  - India first: http://localhost:${port}/india.html`);
    console.log(`  - Data:        http://localhost:${port}/data.html`);
  });
}

if (require.main === module) {
  startServer(DEFAULT_PORT);
}

module.exports = app;


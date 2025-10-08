import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress, Chip } from '@mui/material';

const CandidatesGrid = () => {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);

  const dateFormatter = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  });

  const numberFormatter = new Intl.NumberFormat('en-US');

  useEffect(() => {
    fetch('/api/candidates')
      .then(response => response.json())
      .then(data => {
        setCandidates(data.candidates || []);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching candidates:', error);
        setLoading(false);
      });
  }, []);

  const columns = [
    {
      field: 'date',
      headerName: 'Date',
      width: 120,
      valueFormatter: (params) => params ? dateFormatter.format(new Date(params)) : 'N/A',
    },
    { field: 'rank', headerName: 'Rank', width: 80, type: 'number' },
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    {
      field: 'pre_market_change',
      headerName: 'Pre-Mkt %',
      type: 'number',
      width: 120,
      valueFormatter: (params) => `${params.toFixed(2)}%`,
      cellClassName: (params) => {
        if (params.value == null) return '';
        return params.value >= 0 ? 'profit-positive' : 'profit-negative';
      },
    },
    {
      field: 'volume',
      headerName: 'Volume',
      type: 'number',
      width: 130,
      valueFormatter: (params) => numberFormatter.format(params),
    },
    {
      field: 'relative_volume',
      headerName: 'Rel. Vol',
      type: 'number',
      width: 110,
      valueFormatter: (params) => `${params.toFixed(2)}x`,
    },
    {
      field: 'selected',
      headerName: 'Selected',
      width: 110,
      renderCell: (params) => (
        <Chip
          label={params.value ? 'Yes' : 'No'}
          color={params.value ? 'success' : 'default'}
          size="small"
        />
      ),
    },
    {
      field: 'criteria_met',
      headerName: 'Criteria Met',
      width: 200,
      valueFormatter: (params) => params || 'N/A',
    },
  ];

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box sx={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      p: 2,
    }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Stock Candidates
      </Typography>

      <DataGrid
        rows={candidates}
        columns={columns}
        pageSize={10}
        rowsPerPageOptions={[10, 25, 50]}
        disableSelectionOnClick
        loading={loading}
        sx={{
          height: '100%',
          width: '100%'
        }}
      />
    </Box>
  );
};

export default CandidatesGrid;

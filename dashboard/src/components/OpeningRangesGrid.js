import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress } from '@mui/material';

const OpeningRangesGrid = () => {
  const [ranges, setRanges] = useState([]);
  const [loading, setLoading] = useState(true);

  // Create formatters
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const dateFormatter = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  });

  useEffect(() => {
    fetch('/api/opening-ranges')
      .then(response => response.json())
      .then(data => {
        setRanges(data.opening_ranges || []);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching opening ranges:', error);
        setLoading(false);
      });
  }, []);

  const columns = [
    {
      field: 'date',
      headerName: 'Date',
      width: 150,
      valueFormatter: (params) => params ? dateFormatter.format(new Date(params)) : 'N/A',
    },
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    {
      field: 'timeframe_minutes',
      headerName: 'Timeframe',
      width: 110,
      valueFormatter: (params) => `${params}m`,
    },
    {
      field: 'range_high',
      headerName: 'High',
      type: 'number',
      width: 120,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    {
      field: 'range_low',
      headerName: 'Low',
      type: 'number',
      width: 120,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    {
      field: 'range_size',
      headerName: 'Range Size',
      type: 'number',
      width: 130,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    {
      field: 'range_size_pct',
      headerName: 'Range %',
      type: 'number',
      width: 110,
      valueFormatter: (params) => `${params.toFixed(2)}%`,
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
        Opening Ranges
      </Typography>

      <DataGrid
        rows={ranges}
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

export default OpeningRangesGrid;

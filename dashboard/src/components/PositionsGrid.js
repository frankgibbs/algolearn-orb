import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress } from '@mui/material';

const PositionsGrid = () => {
  const [positions, setPositions] = useState([]);
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
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });

  useEffect(() => {
    fetch('/api/positions')
      .then(response => response.json())
      .then(data => {
        setPositions(data.positions.map((position) => ({
          ...position,
          duration: calculateDuration(position.entry_date, position.exit_date)
        })));
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching positions:', error);
        setLoading(false);
      });
  }, []);

  const calculateDuration = (entryDate, exitDate) => {
    if (!entryDate) return 0;
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : new Date();
    const durationInHours = (end - start) / (1000 * 60 * 60);
    return durationInHours;
  };

  const columns = [
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    { field: 'direction', headerName: 'Direction', width: 90 },
    { field: 'status', headerName: 'Status', width: 90 },
    { field: 'quantity', headerName: 'Quantity', type: 'number', width: 90 },
    {
      field: 'entry_date',
      headerName: 'Entry Date',
      type: 'string',
      width: 200,
      valueFormatter: (params) => params ? dateFormatter.format(new Date(params)) : 'N/A',
    },
    {
      field: 'exit_date',
      headerName: 'Exit Date',
      type: 'string',
      width: 200,
      valueFormatter: (params) => params ? dateFormatter.format(new Date(params)) : 'Open',
    },
    {
      field: 'duration',
      headerName: 'Duration (hours)',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? params.toFixed(2) : '0.00',
    },
    {
      field: 'entry_price',
      headerName: 'Entry Price',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : 'N/A',
    },
    {
      field: 'exit_price',
      headerName: 'Exit Price',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : 'N/A',
    },
    {
      field: 'stop_price',
      headerName: 'Stop Price',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : 'N/A',
    },
    {
      field: 'target_price',
      headerName: 'Target Price',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : 'N/A',
    },
    {
      field: 'margin_required',
      headerName: 'Margin',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : 'N/A',
    },
    {
      field: 'net_profit',
      headerName: 'Net Profit',
      type: 'number',
      width: 120,
      valueFormatter: (params) => params ? usdFormatter.format(params) : usdFormatter.format(0),
      cellClassName: (params) => {
        if (params.value == null) return '';
        return params.value >= 0 ? 'profit-positive' : 'profit-negative';
      },
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
        Positions
      </Typography>

      <DataGrid
        rows={positions}
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

export default PositionsGrid;

import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, Paper, CircularProgress } from '@mui/material';

const TradesGrid = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  // Create a formatter for USD
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const pip_usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
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
    fetch('/api/trades')
      .then(response => response.json())
      .then(data => {
        setTrades(data.trades.map((trade, index) => ({
          id: index,
          ...trade,
          duration: calculateDuration(trade.open_date, trade.close_date)
        })));
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching trades:', error);
        setLoading(false);
      });
  }, []);

  const calculateDuration = (openDate, closeDate) => {
    const start = new Date(openDate);
    const end = new Date(closeDate);
    const durationInHours = (end - start) / (1000 * 60 * 60);
    return durationInHours;
  };

  const columns = [
    { field: 'symbol', headerName: 'Symbol', width: 75 },
    { field: 'direction', headerName: 'Direction', width: 75 },
    { field: 'quantity', headerName: 'Quantity', type: 'number', width: 80 },
    { 
        field: 'open_date', 
        headerName: 'Open Date', 
        type: 'string', 
        width: 200,
        valueFormatter: (params) => dateFormatter.format(new Date(params)),
    },
    { 
        field: 'close_date', 
        headerName: 'Close Date', 
        type: 'string', 
        width: 200,
        valueFormatter: (params) => dateFormatter.format(new Date(params)),
    },
    { 
      field: 'duration', 
      headerName: 'Duration (hours)', 
      type: 'number', 
      width: 100,
      valueFormatter: (params) => params.toFixed(2),
    },
    { 
      field: 'avg_open_price', 
      headerName: 'Open Price', 
      type: 'number', 
      width: 120,
      valueFormatter: (params) => pip_usdFormatter.format(params),
    },
    { 
      field: 'avg_close_price', 
      headerName: 'Close Price', 
      type: 'number', 
      width: 120,
      valueFormatter: (params) => pip_usdFormatter.format(params),
    },
    { 
      field: 'margin_required', 
      headerName: 'Margin', 
      type: 'number', 
      width: 140,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    { 
      field: 'net_profit', 
      headerName: 'Net Profit', 
      type: 'number', 
      width: 120,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    { 
      field: 'net_return', 
      headerName: 'Return %', 
      type: 'number', 
      width: 100,
      valueFormatter: (params) => `${(params * 100).toFixed(2)}%`,
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
        Trades
      </Typography>

        <DataGrid
          rows={trades}
          columns={columns}
          pageSize={5}
          rowsPerPageOptions={[5]}
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

export default TradesGrid;
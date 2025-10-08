import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress } from '@mui/material';

const TradeSummaryGrid = () => {
  const [tradeSummary, setTradeSummary] = useState([]);
  const [loading, setLoading] = useState(true);

  // Formatter for USD
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  useEffect(() => {
    fetch('/api/trades')
      .then(response => response.json())
      .then(data => {
        const summary = summarizeTrades(data.trades);
        setTradeSummary(summary);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching trades:', error);
        setLoading(false);
      });
  }, []);

  const summarizeTrades = (trades) => {
    console.log(trades);
    const summaryMap = trades.reduce((acc, trade) => {
      const date = new Date(trade.close_date).toLocaleDateString();
      if (!acc[date]) {
        acc[date] = { date, net_profit: 0, net_return: 0, total_lot_size: 0, trade_count: 0, wins: 0, losses: 0 };
      }
      acc[date].net_profit += trade.net_profit;
      acc[date].net_return += trade.net_return;
      acc[date].total_lot_size += trade.quantity;
      acc[date].trade_count += 1;
      if (trade.net_profit > 0) {
        acc[date].wins += 1;
      } else if (trade.net_profit < 0) {
        acc[date].losses += 1;
      }
      return acc;
    }, {});

    // Convert the summary map to an array and calculate average lot size and win percentage
    return Object.entries(summaryMap).map(([date, summary], index) => ({
      id: index,  // Assign a unique id based on the index
      ...summary,
      avg_lot_size: summary.total_lot_size / summary.trade_count,  // Calculate average lot size
      win_percentage: (summary.wins / summary.trade_count) * 100,  // Calculate win percentage
    }));
  };

  const columns = [
    { field: 'date', headerName: 'Date', width: 150 },
    { 
      field: 'net_profit', 
      headerName: 'Net Profit', 
      type: 'number', 
      width: 150,
      valueFormatter: (params) => usdFormatter.format(params),
    },
    { 
      field: 'net_return', 
      headerName: 'Net Return %', 
      type: 'number', 
      width: 150,
      valueFormatter: (params) => `${(params * 100).toFixed(2)}%`,
    },
    { 
      field: 'trade_count', 
      headerName: 'Trade Count', 
      type: 'number', 
      width: 150,
    },

    { 
      field: 'win_percentage', 
      headerName: 'Win %', 
      type: 'number', 
      width: 150,
      valueFormatter: (params) => `${params.toFixed(0)}%`,
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
        Daily Trade Summary
      </Typography>

      <DataGrid
        rows={tradeSummary}
        columns={columns}
        pageSize={5}
        rowsPerPageOptions={[5]}
        disableSelectionOnClick
        sx={{ 
          height: '100%', 
          width: '100%'
        }}
      />
    </Box>
  );
};

export default TradeSummaryGrid;

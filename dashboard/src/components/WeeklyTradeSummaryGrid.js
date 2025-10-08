import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress } from '@mui/material';

const WeeklyTradeSummaryGrid = () => {
  const [tradeSummary, setTradeSummary] = useState([]);
  const [loading, setLoading] = useState(true);

  // Formatter for USD
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const getWeekBounds = (date) => {
    const d = new Date(date);
    const day = d.getDay();
    
    // Adjust to previous Sunday (week start)
    const sunday = new Date(d);
    sunday.setDate(d.getDate() - day);
    
    // Get following Friday (week end)
    const friday = new Date(sunday);
    friday.setDate(sunday.getDate() + 5);
    
    return {
      start: sunday.toLocaleDateString(),
      end: friday.toLocaleDateString()
    };
  };

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
    const summaryMap = trades.reduce((acc, trade) => {
      const weekBounds = getWeekBounds(trade.close_date);
      const weekKey = `${weekBounds.start}`;
      
      if (!acc[weekKey]) {
        acc[weekKey] = {
          date: weekKey,
          net_profit: 0,
          net_return: 0,
          total_lot_size: 0,
          trade_count: 0,
          wins: 0,
          losses: 0
        };
      }
      
      acc[weekKey].net_profit += trade.net_profit;
      acc[weekKey].net_return += trade.net_return;
      acc[weekKey].total_lot_size += trade.quantity;
      acc[weekKey].trade_count += 1;
      if (trade.net_profit > 0) {
        acc[weekKey].wins += 1;
      } else if (trade.net_profit < 0) {
        acc[weekKey].losses += 1;
      }
      return acc;
    }, {});

    return Object.entries(summaryMap)
      .map(([date, summary], index) => ({
        id: index,
        ...summary,
        avg_lot_size: summary.total_lot_size / summary.trade_count,
        win_percentage: (summary.wins / summary.trade_count) * 100,
      }))
      .sort((a, b) => new Date(a.date.split(' - ')[0]) - new Date(b.date.split(' - ')[0]));
  };

  const columns = [
    { field: 'date', headerName: 'Week', width: 200 },
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
        Weekly Trade Summary
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

export default WeeklyTradeSummaryGrid;

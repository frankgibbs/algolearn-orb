import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, CircularProgress } from '@mui/material';

const DailySummaryGrid = () => {
  const [dailySummary, setDailySummary] = useState([]);
  const [loading, setLoading] = useState(true);

  // Formatter for USD
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  useEffect(() => {
    fetch('/api/positions')
      .then(response => response.json())
      .then(data => {
        const summary = summarizePositions(data.positions);
        setDailySummary(summary);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching positions:', error);
        setLoading(false);
      });
  }, []);

  const summarizePositions = (positions) => {
    // Only include closed positions with exit dates
    const closedPositions = positions.filter(pos => pos.status === 'CLOSED' && pos.exit_date);

    const summaryMap = closedPositions.reduce((acc, position) => {
      const date = new Date(position.exit_date).toLocaleDateString();
      if (!acc[date]) {
        acc[date] = {
          date,
          net_profit: 0,
          total_cost_basis: 0,
          position_count: 0,
          wins: 0,
          losses: 0
        };
      }

      const profit = position.net_profit || 0;
      const cost_basis = (position.quantity || 0) * (position.entry_price || 0);

      acc[date].net_profit += profit;
      acc[date].total_cost_basis += cost_basis;
      acc[date].position_count += 1;

      if (profit > 0) {
        acc[date].wins += 1;
      } else if (profit < 0) {
        acc[date].losses += 1;
      }

      return acc;
    }, {});

    // Convert the summary map to an array and calculate metrics
    return Object.entries(summaryMap).map(([date, summary], index) => ({
      id: index,
      ...summary,
      net_return: summary.total_cost_basis > 0 ? summary.net_profit / summary.total_cost_basis : 0,
      win_percentage: summary.position_count > 0 ? (summary.wins / summary.position_count) * 100 : 0,
    })).sort((a, b) => new Date(b.date) - new Date(a.date)); // Sort by date descending
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
      field: 'position_count',
      headerName: 'Positions',
      type: 'number',
      width: 120,
    },
    {
      field: 'wins',
      headerName: 'Wins',
      type: 'number',
      width: 100,
    },
    {
      field: 'losses',
      headerName: 'Losses',
      type: 'number',
      width: 100,
    },
    {
      field: 'win_percentage',
      headerName: 'Win %',
      type: 'number',
      width: 120,
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
        Daily Summary
      </Typography>

      <DataGrid
        rows={dailySummary}
        columns={columns}
        pageSize={10}
        rowsPerPageOptions={[10, 25]}
        disableSelectionOnClick
        sx={{
          height: '100%',
          width: '100%'
        }}
      />
    </Box>
  );
};

export default DailySummaryGrid;

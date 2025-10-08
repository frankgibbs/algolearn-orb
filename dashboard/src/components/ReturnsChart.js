import React, { useState, useEffect } from 'react';
import { LineChart } from '@mui/x-charts/LineChart';
import { Box, Typography, CircularProgress, Paper } from '@mui/material';

const ReturnsChart = () => {
  const [profitChartData, setProfitChartData] = useState(null);
  const [returnChartData, setReturnChartData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/positions')
      .then(response => response.json())
      .then(data => {
        const positions = data.positions.filter(pos => pos.status === 'CLOSED' && pos.exit_date);

        // Group positions by date and calculate daily net profit and net return
        const dailyData = positions.reduce((acc, position) => {
          const date = new Date(position.exit_date).toLocaleDateString();
          if (!acc[date]) {
            acc[date] = { net_profit: 0, total_cost_basis: 0 };
          }
          const cost_basis = (position.quantity || 0) * (position.entry_price || 0);
          acc[date].net_profit += (position.net_profit || 0);
          acc[date].total_cost_basis += cost_basis;
          return acc;
        }, {});

        // Sort dates and calculate cumulative net profit and net return
        const sortedDates = Object.keys(dailyData).sort((a, b) => new Date(a) - new Date(b));
        let cumulativeProfit = 0;
        let cumulativeCostBasis = 0;
        const xAxis = [];
        const profitYAxis = [];
        const returnYAxis = [];

        sortedDates.forEach(date => {
          cumulativeProfit += dailyData[date].net_profit;
          cumulativeCostBasis += dailyData[date].total_cost_basis;
          const cumulativeReturn = cumulativeCostBasis > 0
            ? (cumulativeProfit / cumulativeCostBasis) * 100
            : 0;
          xAxis.push(date);
          profitYAxis.push(cumulativeProfit);
          returnYAxis.push(cumulativeReturn);
        });

        setProfitChartData({ xAxis, yAxis: profitYAxis });
        setReturnChartData({ xAxis, yAxis: returnYAxis });
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching positions:', error);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box sx={{ 
      mb: 2, 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center',
    }}>
      <Typography variant="h6" component="h2" gutterBottom>
        PNL (USD)
      </Typography>
      <Paper elevation={3} sx={{ p: 2, width: '80%' }}>
        {profitChartData && (
          <LineChart
            xAxis={[{ 
              data: profitChartData.xAxis, 
              scaleType: 'point',
              tickLabelStyle: { angle: 45, textAnchor: 'start', fontSize: 12 }
            }]}
            series={[
              {
                data: profitChartData.yAxis,
                area: true,
                label: 'Cumulative Net Profit',
                valueFormatter: (value) => `$${value.toFixed(2)}`,
                color: '#6e93a6', // Green color
              },
            ]}
            height={300}
            margin={{ top: 10, bottom: 70, left: 40, right: 10 }}
            slotProps={{
              legend: {
                hidden: true,
              },
            }}
          />
        )}
      </Paper>
      
      <Typography sx={{ mt: 4}}variant="h6" component="h2" gutterBottom>
        Returns (%)
      </Typography>
      <Paper elevation={3} sx={{ p: 2, width: '80%' }}>
        {returnChartData && (
          <LineChart
            xAxis={[{ 
              data: returnChartData.xAxis, 
              scaleType: 'point',
              tickLabelStyle: { angle: 45, textAnchor: 'start', fontSize: 12 }
            }]}
            series={[
              {
                data: returnChartData.yAxis,
                area: true,
                label: 'Cumulative Net Return',
                valueFormatter: (value) => `${value.toFixed(2)}%`, // Adjusted to display percentages
                color: '#ff7f0e', // Orange color
              },
            ]}
            height={300}
            margin={{ top: 10, bottom: 70, left: 40, right: 10 }}
            slotProps={{
              legend: {
                hidden: true,
              },
            }}
          />
        )}
      </Paper>
    </Box>
  );
};

export default ReturnsChart;
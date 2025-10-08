import React, { useState, useEffect } from 'react';
import { Typography, Box, CircularProgress, Table, TableBody, TableCell, TableContainer, TableRow, Paper } from '@mui/material';

const PositionsSummary = () => {
  const [totalNetProfit, setTotalNetProfit] = useState(0);
  const [totalNetReturn, setTotalNetReturn] = useState(0);
  const [todayNetProfit, setTodayNetProfit] = useState(0);
  const [todayNetReturn, setTodayNetReturn] = useState(0);
  const [activePositions, setActivePositions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [accountBalance, setAccountBalance] = useState(0);

  // Create formatters
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const percentFormatter = new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  useEffect(() => {
    // Fetch positions data
    fetch('/api/positions')
      .then(response => response.json())
      .then(data => {
        const positions = data.positions;

        // Filter closed positions for P&L calculation - must have exit_date to be truly closed
        const closedPositions = positions.filter(pos => pos.status === 'CLOSED' && pos.exit_date);

        // Calculate totals using cost basis (quantity * entry_price)
        const netProfit = closedPositions.reduce((sum, pos) => sum + (pos.net_profit || 0), 0);
        const totalCostBasis = closedPositions.reduce((sum, pos) => {
          const cost = (pos.quantity || 0) * (pos.entry_price || 0);
          return sum + cost;
        }, 0);
        const netReturn = totalCostBasis > 0 ? netProfit / totalCostBasis : 0;

        // Calculate today's totals
        const today = new Date().toLocaleDateString();
        const todayPositions = closedPositions.filter(pos =>
          pos.exit_date && new Date(pos.exit_date).toLocaleDateString() === today
        );
        const todayProfit = todayPositions.reduce((sum, pos) => sum + (pos.net_profit || 0), 0);
        const todayCostBasis = todayPositions.reduce((sum, pos) => {
          const cost = (pos.quantity || 0) * (pos.entry_price || 0);
          return sum + cost;
        }, 0);
        const todayReturn = todayCostBasis > 0 ? todayProfit / todayCostBasis : 0;

        // Count active positions (OPEN or PENDING)
        const active = positions.filter(pos => pos.status === 'OPEN' || pos.status === 'PENDING').length;

        setTotalNetProfit(netProfit);
        setTotalNetReturn(netReturn);
        setTodayNetProfit(todayProfit);
        setTodayNetReturn(todayReturn);
        setActivePositions(active);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching positions:', error);
        setLoading(false);
      });

    // Fetch config data for account balance
    fetch('/api/config')
      .then(response => response.json())
      .then(config => {
        setAccountBalance(config.FIELD_ACCOUNT_BALANCE || 0);
      })
      .catch(error => {
        console.error('Error fetching config:', error);
      });
  }, []);

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box sx={{
      p: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Summary
      </Typography>
      <TableContainer component={Paper} sx={{ width: '90%' }}>
        <Table size="small">
          <TableBody>
            <TableRow>
              <TableCell><Typography variant="body2">Today's Net Profit</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(todayNetProfit)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Today's Return %</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{percentFormatter.format(todayNetReturn)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Total Net Profit</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(totalNetProfit)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Total Return %</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{percentFormatter.format(totalNetReturn)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Active Positions</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{activePositions}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Account Balance</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(accountBalance)}</Typography></TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default PositionsSummary;

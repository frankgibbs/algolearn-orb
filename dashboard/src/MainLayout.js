import React, { useState } from 'react';
import Header from './Header';
import './App.css'; // Assuming you have global CSS here
import PositionsGrid from './components/PositionsGrid';
import PositionsSummary from './components/PositionsSummary';
import ReturnsChart from './components/ReturnsChart';
import DailySummaryGrid from './components/DailySummaryGrid';
import OpeningRangesGrid from './components/OpeningRangesGrid';
import CandidatesGrid from './components/CandidatesGrid';
import { Tabs, Tab, Box } from '@mui/material';

function MainLayout() {
  const [activeTab, setActiveTab] = useState(0);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  return (
    <div className="main-layout dark-mode">
      {/* Section 1 */}
      <div className="section-header">
        <Header />
      </div>

      <div className="section-left">
        <PositionsSummary />
        <ReturnsChart />
      </div>

      {/* Section 3 */}
      <div className="section-main">
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="stock tabs">
          <Tab label="Daily Summary" />
          <Tab label="Position Details" />
          <Tab label="Opening Ranges" />
          <Tab label="Candidates" />
        </Tabs>
        <Box className="tab-content">
          {activeTab === 0 && <DailySummaryGrid />}
          {activeTab === 1 && <PositionsGrid />}
          {activeTab === 2 && <OpeningRangesGrid />}
          {activeTab === 3 && <CandidatesGrid />}
        </Box>
      </div>
    </div>
  );
}

export default MainLayout;

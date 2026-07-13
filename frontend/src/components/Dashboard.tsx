import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { useAuth } from "../contexts/AuthContext.new";

const PROPERTIES = [
  { id: 'prop-001', name: 'Beach House Alpha', tenantId: 'tenant-a' },
  { id: 'prop-002', name: 'City Apartment Downtown', tenantId: 'tenant-a' },
  { id: 'prop-003', name: 'Country Villa Estate', tenantId: 'tenant-a' },
  { id: 'prop-004', name: 'Lakeside Cottage', tenantId: 'tenant-b' },
  { id: 'prop-005', name: 'Urban Loft Modern', tenantId: 'tenant-b' }
];

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const availableProperties = PROPERTIES.filter((property) => property.tenantId === user?.tenant_id);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [period, setPeriod] = useState('2024-03');
  const [year, month] = period.split('-').map(Number);

  useEffect(() => {
    if (!availableProperties.some((property) => property.id === selectedProperty)) {
      setSelectedProperty(availableProperties[0]?.id || '');
    }
  }, [availableProperties, selectedProperty]);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end gap-3">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {availableProperties.map((property) => (
                    <option key={property.id} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
                <label className="text-xs font-medium text-gray-700">Reporting month</label>
                <input
                  type="month"
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                  className="block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                />
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {selectedProperty && <RevenueSummary propertyId={selectedProperty} month={month} year={year} />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;

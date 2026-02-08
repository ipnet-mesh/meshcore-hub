/**
 * MeshCore Hub - Main Map Page
 *
 * Full map functionality with filters, markers, and clustering.
 * Requires Leaflet.js to be loaded before this script.
 *
 * Configuration:
 * - Set window.mapConfig.logoUrl before loading this script
 * - Set window.mapConfig.dataUrl for the data endpoint (default: '/map/data')
 */

(function() {
    'use strict';

    // Configuration (can be set before script loads)
    var config = window.mapConfig || {};
    var logoUrl = config.logoUrl || '/static/img/logo.svg';
    var dataUrl = config.dataUrl || '/map/data';

    // Initialize map with world view (will be centered on nodes once loaded)
    var map = L.map('map').setView([0, 0], 2);

    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Store all nodes and markers
    var allNodes = [];
    var allMembers = [];
    var markers = [];
    var mapCenter = { lat: 0, lon: 0 };
    var infraCenter = null;

    // Maximum radius (km) from anchor point for bounds calculation
    var MAX_BOUNDS_RADIUS_KM = 20;

    // Padding for fitBounds - more padding on mobile for tighter zoom
    var isMobilePortrait = window.innerWidth < 480;
    var isMobile = window.innerWidth < 768;
    var BOUNDS_PADDING = isMobilePortrait ? [50, 50] : (isMobile ? [75, 75] : [100, 100]);

    /**
     * Calculate distance between two points in km (Haversine formula)
     */
    function getDistanceKm(lat1, lon1, lat2, lon2) {
        var R = 6371; // Earth's radius in km
        var dLat = (lat2 - lat1) * Math.PI / 180;
        var dLon = (lon2 - lon1) * Math.PI / 180;
        var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon/2) * Math.sin(dLon/2);
        var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    /**
     * Filter nodes within radius of anchor point for bounds calculation
     */
    function getNodesWithinRadius(nodes, anchorLat, anchorLon, radiusKm) {
        return nodes.filter(function(n) {
            return getDistanceKm(anchorLat, anchorLon, n.lat, n.lon) <= radiusKm;
        });
    }

    /**
     * Get anchor point for bounds calculation (infra center or nodes center)
     */
    function getAnchorPoint(nodes) {
        if (infraCenter) {
            return infraCenter;
        }
        // Fall back to center of provided nodes
        if (nodes.length === 0) return { lat: 0, lon: 0 };
        return {
            lat: nodes.reduce(function(sum, n) { return sum + n.lat; }, 0) / nodes.length,
            lon: nodes.reduce(function(sum, n) { return sum + n.lon; }, 0) / nodes.length
        };
    }

    /**
     * Normalize adv_type to lowercase for consistent comparison
     */
    function normalizeType(type) {
        return type ? type.toLowerCase() : null;
    }

    /**
     * Get display name for node type
     */
    function getTypeDisplay(node) {
        var type = normalizeType(node.adv_type);
        if (type === 'chat') return 'Chat';
        if (type === 'repeater') return 'Repeater';
        if (type === 'room') return 'Room';
        return type ? type.charAt(0).toUpperCase() + type.slice(1) : 'Unknown';
    }

    /**
     * Create marker icon for a node
     */
    function createNodeIcon(node) {
        var displayName = node.name || '';
        var relativeTime = typeof formatRelativeTime === 'function' ? formatRelativeTime(node.last_seen) : '';
        var timeDisplay = relativeTime ? ' (' + relativeTime + ')' : '';

        // Use red circle for infrastructure nodes, blue circle for others
        var iconHtml;
        if (node.is_infra) {
            iconHtml = '<div style="width: 12px; height: 12px; background: #ef4444; border: 2px solid #b91c1c; border-radius: 50%; box-shadow: 0 0 4px rgba(239,68,68,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';
        } else {
            iconHtml = '<div style="width: 12px; height: 12px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';
        }

        return L.divIcon({
            className: 'custom-div-icon',
            html: '<div class="map-marker" style="display: flex; flex-direction: column; align-items: center; gap: 2px;">' +
                iconHtml +
                '<span class="map-label" style="font-size: 10px; font-weight: bold; color: #fff; background: rgba(0,0,0,0.5); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-align: center;">' + displayName + timeDisplay + '</span>' +
            '</div>',
            iconSize: [120, 50],
            iconAnchor: [60, 12]
        });
    }

    /**
     * Get type emoji for node
     */
    function getTypeEmoji(node) {
        var type = normalizeType(node.adv_type);
        if (type === 'chat') return '💬';
        if (type === 'repeater') return '📡';
        if (type === 'room') return '🪧';
        return '📍';
    }

    /**
     * Create popup content for a node
     */
    function createPopupContent(node) {
        var ownerHtml = '';
        if (node.owner) {
            var ownerDisplay = node.owner.callsign
                ? node.owner.name + ' (' + node.owner.callsign + ')'
                : node.owner.name;
            ownerHtml = '<p><span class="opacity-70">Owner:</span> ' + ownerDisplay + '</p>';
        }

        var roleHtml = '';
        if (node.role) {
            roleHtml = '<p><span class="opacity-70">Role:</span> <span class="badge badge-xs badge-ghost">' + node.role + '</span></p>';
        }

        var typeDisplay = getTypeDisplay(node);
        var typeEmoji = getTypeEmoji(node);

        // Infra indicator (red/blue dot) shown to the right of the title if is_infra is defined
        var infraIndicatorHtml = '';
        if (typeof node.is_infra !== 'undefined') {
            var dotColor = node.is_infra ? '#ef4444' : '#3b82f6';
            var borderColor = node.is_infra ? '#b91c1c' : '#1e40af';
            var title = node.is_infra ? 'Infrastructure' : 'Public';
            infraIndicatorHtml = ' <span style="display: inline-block; width: 10px; height: 10px; background: ' + dotColor + '; border: 2px solid ' + borderColor + '; border-radius: 50%; vertical-align: middle;" title="' + title + '"></span>';
        }

        var lastSeenHtml = node.last_seen
            ? '<p><span class="opacity-70">Last seen:</span> ' + node.last_seen.substring(0, 19).replace('T', ' ') + '</p>'
            : '';

        return '<div class="p-2">' +
            '<h3 class="font-bold text-lg mb-2">' + typeEmoji + ' ' + node.name + infraIndicatorHtml + '</h3>' +
            '<div class="space-y-1 text-sm">' +
                '<p><span class="opacity-70">Type:</span> ' + typeDisplay + '</p>' +
                roleHtml +
                ownerHtml +
                '<p><span class="opacity-70">Key:</span> <code class="text-xs">' + node.public_key.substring(0, 16) + '...</code></p>' +
                '<p><span class="opacity-70">Location:</span> ' + node.lat.toFixed(4) + ', ' + node.lon.toFixed(4) + '</p>' +
                lastSeenHtml +
            '</div>' +
            '<a href="/nodes/' + node.public_key + '" class="btn btn-outline btn-xs mt-3">View Details</a>' +
        '</div>';
    }

    /**
     * Clear all markers from map
     */
    function clearMarkers() {
        markers.forEach(function(marker) {
            map.removeLayer(marker);
        });
        markers = [];
    }

    /**
     * Core filter logic - returns filtered nodes and updates markers
     */
    function applyFiltersCore() {
        var categoryFilter = document.getElementById('filter-category').value;
        var typeFilter = document.getElementById('filter-type').value;
        var memberFilter = document.getElementById('filter-member').value;

        // Filter nodes
        var filteredNodes = allNodes.filter(function(node) {
            // Category filter (infrastructure only)
            if (categoryFilter === 'infra' && !node.is_infra) return false;

            // Type filter (case-insensitive)
            var nodeType = normalizeType(node.adv_type);
            if (typeFilter && nodeType !== typeFilter) return false;

            // Member filter - match node's member_id tag to selected member_id
            if (memberFilter) {
                if (node.member_id !== memberFilter) return false;
            }

            return true;
        });

        // Clear existing markers
        clearMarkers();

        // Add filtered markers
        filteredNodes.forEach(function(node) {
            var marker = L.marker([node.lat, node.lon], { icon: createNodeIcon(node) }).addTo(map);
            marker.bindPopup(createPopupContent(node));
            markers.push(marker);
        });

        // Update counts
        var countEl = document.getElementById('node-count');
        var filteredEl = document.getElementById('filtered-count');

        if (filteredNodes.length === allNodes.length) {
            countEl.textContent = allNodes.length + ' nodes on map';
            filteredEl.classList.add('hidden');
        } else {
            countEl.textContent = allNodes.length + ' total';
            filteredEl.textContent = filteredNodes.length + ' shown';
            filteredEl.classList.remove('hidden');
        }

        return filteredNodes;
    }

    /**
     * Apply filters and recenter map on filtered nodes
     */
    function applyFilters() {
        var filteredNodes = applyFiltersCore();
        var categoryFilter = document.getElementById('filter-category').value;

        // Fit bounds if we have filtered nodes
        if (filteredNodes.length > 0) {
            var nodesToFit = filteredNodes;

            // Apply radius filter when showing all nodes (not infra-only)
            if (categoryFilter !== 'infra') {
                var anchor = getAnchorPoint(filteredNodes);
                var nearbyNodes = getNodesWithinRadius(filteredNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
                if (nearbyNodes.length > 0) {
                    nodesToFit = nearbyNodes;
                }
            }

            var bounds = L.latLngBounds(nodesToFit.map(function(n) { return [n.lat, n.lon]; }));
            map.fitBounds(bounds, { padding: BOUNDS_PADDING });
        } else if (mapCenter.lat !== 0 || mapCenter.lon !== 0) {
            map.setView([mapCenter.lat, mapCenter.lon], 10);
        }
    }

    /**
     * Apply filters without recentering (for initial load after manual center)
     */
    function applyFiltersNoRecenter() {
        applyFiltersCore();
    }

    /**
     * Populate member filter dropdown
     */
    function populateMemberFilter() {
        var select = document.getElementById('filter-member');

        // Sort members by name
        var sortedMembers = allMembers.slice().sort(function(a, b) {
            return a.name.localeCompare(b.name);
        });

        // Add options for all members
        sortedMembers.forEach(function(member) {
            if (member.member_id) {
                var option = document.createElement('option');
                option.value = member.member_id;
                option.textContent = member.callsign
                    ? member.name + ' (' + member.callsign + ')'
                    : member.name;
                select.appendChild(option);
            }
        });
    }

    /**
     * Clear all filters
     */
    function clearFilters() {
        document.getElementById('filter-category').value = '';
        document.getElementById('filter-type').value = '';
        document.getElementById('filter-member').value = '';
        document.getElementById('show-labels').checked = false;
        updateLabelVisibility();
        applyFilters();
    }

    /**
     * Toggle label visibility
     */
    function updateLabelVisibility() {
        var showLabels = document.getElementById('show-labels').checked;
        var mapEl = document.getElementById('map');
        if (showLabels) {
            mapEl.classList.add('show-labels');
        } else {
            mapEl.classList.remove('show-labels');
        }
    }

    // Event listeners for filters
    document.getElementById('filter-category').addEventListener('change', applyFilters);
    document.getElementById('filter-type').addEventListener('change', applyFilters);
    document.getElementById('filter-member').addEventListener('change', applyFilters);
    document.getElementById('show-labels').addEventListener('change', updateLabelVisibility);
    document.getElementById('clear-filters').addEventListener('click', clearFilters);

    // Fetch and display nodes
    fetch(dataUrl)
        .then(function(response) { return response.json(); })
        .then(function(data) {
            allNodes = data.nodes;
            allMembers = data.members || [];
            mapCenter = data.center;
            infraCenter = data.infra_center;

            // Log debug info
            var debug = data.debug || {};
            console.log('Map data loaded:', debug);
            console.log('Sample node data:', allNodes.length > 0 ? allNodes[0] : 'No nodes');

            if (debug.error) {
                document.getElementById('node-count').textContent = 'Error: ' + debug.error;
                return;
            }

            if (debug.total_nodes === 0) {
                document.getElementById('node-count').textContent = 'No nodes in database';
                return;
            }

            if (debug.nodes_with_coords === 0) {
                document.getElementById('node-count').textContent = debug.total_nodes + ' nodes (none have coordinates)';
                return;
            }

            // Populate member filter
            populateMemberFilter();

            // Initial display - center map on infrastructure nodes if available, else nodes within radius
            var infraNodes = allNodes.filter(function(n) { return n.is_infra; });
            if (infraNodes.length > 0) {
                var bounds = L.latLngBounds(infraNodes.map(function(n) { return [n.lat, n.lon]; }));
                map.fitBounds(bounds, { padding: BOUNDS_PADDING });
            } else if (allNodes.length > 0) {
                // Use radius filter to exclude outliers
                var anchor = getAnchorPoint(allNodes);
                var nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
                var nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
                var bounds = L.latLngBounds(nodesToFit.map(function(n) { return [n.lat, n.lon]; }));
                map.fitBounds(bounds, { padding: BOUNDS_PADDING });
            }

            // Apply filters (won't re-center since we just did above)
            applyFiltersNoRecenter();
        })
        .catch(function(error) {
            console.error('Error loading map data:', error);
            document.getElementById('node-count').textContent = 'Error loading data';
        });
})();

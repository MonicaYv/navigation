const token =
"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGFyc2hzYWh1NTY3QGdtYWlsLmNvbSIsImV4cCI6MTc1NDQxMzE5MH0.R2AXT-DrYP39Mt_Iza4Q15mKGvEzYySqXFGWwH5G3YY";
const apiBase = "/api/geofences";
const authKey = "GWG$%$fg365vhgfh6$*&^25dhERYET";

const map = L.map("map").setView([19.076, 72.8777], 11);
L.tileLayer("http://192.168.1.110:4090/styles/maptiler-basic/256/{z}/{x}/{y}.png").addTo(map);

const drawnItems = new L.FeatureGroup().addTo(map);
const drawControl = new L.Control.Draw({
    draw: {
        polyline: false,
        rectangle: false,
        circle: false,
        marker: false,
        polygon: { allowIntersection: false, showArea: true },
    },
    edit: { featureGroup: drawnItems },
});
map.addControl(drawControl);

const log = (msg) => {
    document.getElementById("log").innerText =
        `[${new Date().toLocaleTimeString()}] ${msg}\n` +
        document.getElementById("log").innerText;
};

map.on(L.Draw.Event.CREATED, async (e) => {
    const layer = e.layer;
    drawnItems.addLayer(layer);

    const coords = layer.getLatLngs()[0].map((p) => [p.lng, p.lat]);
    const body = {
        name: prompt("Enter Geofence Name:") || "Unnamed",
        coordinates: coords,
        metadata: { created_by: "Test UI" },
    };

    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);
        myHeaders.append("Content-Type", "application/json");

        const res = await fetch(apiBase, {
            method: "POST",
            headers: myHeaders,
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`HTTP ${res.status}: ${errorText}`);
        }

        const data = await res.json();
        log(`Geofence Created: ${JSON.stringify(data)}`);
    } catch (err) {
        log("Error creating geofence: " + err.message);
    }
});

map.on("click", async (e) => {
    const point = { lat: e.latlng.lat, lon: e.latlng.lng };
    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);
        myHeaders.append("Content-Type", "application/json");

        const res = await fetch(`${apiBase}/status`, {
            method: "POST",
            headers: myHeaders,
            body: JSON.stringify(point),
        });

        if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`HTTP ${res.status}: ${errorText}`);
        }

        const data = await res.json();
        if (data.inside_geofences.length) {
            log(
                `Inside Geofences: ${data.inside_geofences
                    .map((z) => z.name)
                    .join(", ")}`
            );
        } else {
            log("Outside all geofences");
        }
    } catch (err) {
        log("Error checking geofence status: " + err.message);
    }
});

map.on("draw:edited", async function (e) {
    e.layers.eachLayer(async (layer) => {
        const id = layer._geofenceId;
        if (!id) return;

        const coords = layer.getLatLngs()[0].map(p => [p.lng, p.lat]);
        const payload = {
            name: `Geofence ${id}`,
            coordinates: coords
        };

        try {
            const myHeaders = new Headers();
            myHeaders.append("authorization-key", authKey);
            myHeaders.append("Authorization", `Bearer ${token}`);
            myHeaders.append("Content-Type", "application/json");

            await fetch(`/api/geofences/${id}`, {
                method: "PUT",
                headers: myHeaders,
                body: JSON.stringify(payload)
            });

            log(`Updated geofence ${id}`);
        } catch (err) {
            log("Error updating geofence: " + err.message);
        }
    });
});


async function loadGeofences() {
    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);

        const res = await fetch(`${apiBase}/list`, {
            headers: myHeaders,
        });

        if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`HTTP ${res.status}: ${errorText}`);
        }

        const data = await res.json();
        data.forEach((gf) => {
            const parsed = wellknown.parse(gf.geom); // parse WKT to GeoJSON
            if (parsed && parsed.coordinates) {
                const coords = parsed.coordinates[0]; // exterior ring of polygon
                const latlngs = coords.map(p => [p[1], p[0]]); // [lng,lat] -> [lat,lng]
                const polygon = L.polygon(latlngs, { color: "blue" });
                drawnItems.addLayer(polygon);
            }
        });
        log(`Loaded ${data.length} geofences`);
    } catch (err) {
        log("Error loading geofences: " + err.message);
    }
}

async function addGeofenceById() {
    const id = document.getElementById("geofenceIdInput").value;
    if (!id) return alert("Enter a Geofence ID");

    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);
        const res = await fetch(`/api/geofences/${id}`, { headers: myHeaders });
        if (!res.ok) throw new Error(await res.text());
        const gf = await res.json();
        const parsed = wellknown.parse(gf.geom);
        if (parsed && parsed.coordinates) {
            const coords = parsed.coordinates[0];
            const latlngs = coords.map(p => [p[1], p[0]]);
            const polygon = L.polygon(latlngs, { color: "green" });
            polygon._geofenceId = gf.id; // store for deletion
            drawnItems.addLayer(polygon);
        }
    } catch (err) {
        console.error("Error loading geofence by ID", err);
        alert("Failed to load geofence");
    }
}

async function deleteGeofencebyID() {
    const id = document.getElementById("geofenceIdInput").value;
    if (!id) return alert("Enter a Geofence ID");

    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);

        const res = await fetch(`/api/geofences/${id}`, {
            method: "DELETE",
            headers: myHeaders
        });

        if (!res.ok) throw new Error(await res.text());

        alert(`Geofence ${id} deleted successfully`);
        // Optionally remove it from map if it's visible:
        drawnItems.eachLayer(layer => {
            if (layer._geofenceId == id) drawnItems.removeLayer(layer);
        });
        reloadGeofences();

    } catch (err) {
        console.error("Error deleting geofence by ID", err);
        alert("Failed to delete geofence");
    }
}

async function reloadGeofences() {
    try {
        const myHeaders = new Headers();
        myHeaders.append("authorization-key", authKey);
        myHeaders.append("Authorization", `Bearer ${token}`);

        const res = await fetch("/api/geofences/list", { headers: myHeaders });
        if (!res.ok) throw new Error(await res.text());

        const data = await res.json();

        // Clear existing geofence layers
        drawnItems.eachLayer(layer => {
            if (layer._geofenceId) drawnItems.removeLayer(layer);
        });

        // Draw fetched geofences
        data.forEach(gf => {
            const parsed = wellknown.parse(gf.geom);
            if (parsed && parsed.coordinates) {
                const coords = parsed.coordinates[0];
                const latlngs = coords.map(p => [p[1], p[0]]);
                const polygon = L.polygon(latlngs, { color: "blue" });
                polygon._geofenceId = gf.id;
                drawnItems.addLayer(polygon);
            }
        });

        console.log(`Loaded ${data.length} geofences`);
    } catch (err) {
        console.error("Error loading geofences:", err);
        alert("Failed to load geofences");
    }
}


loadGeofences();


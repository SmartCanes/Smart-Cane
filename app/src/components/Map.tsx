import { MapContainer, TileLayer, Marker } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useState } from "react";

export default function Map() {
  const [route, setRoute] = useState([]);

  //   const fetchRoute = async () => {
  //     const start = "14.656,121.041";
  //     const end = "14.657,121.045";
  //     const response = await fetch(
  //       `http://localhost:8989/route?point=${start}&point=${end}&vehicle=car&points_encoded=false`
  //     );
  //     const data = await response.json();
  //     const coords = data.paths[0].points.coordinates.map(([lng, lat]) => [
  //       lat,
  //       lng,
  //     ]);
  //     setRoute(coords);
  //   };

  const bounds = [
    [14.65, 121.035],
    [14.662, 121.048],
  ];

  return (
    <div style={{ height: "100vh", width: "100%" }}>
      <MapContainer
        zoom={15}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
        maxBoundsViscosity={1.0}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
      </MapContainer>
    </div>
  );
}

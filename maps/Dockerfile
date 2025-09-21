FROM openjdk:21-jdk-slim

WORKDIR /app

COPY graphhopper-web-10.0.jar ./graphhopper.jar

COPY config/config.yml ./config.yml
COPY data/novaliches.osm.pbf ./novaliches.osm.pbf

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

EXPOSE 8989

ENTRYPOINT ["./entrypoint.sh"]

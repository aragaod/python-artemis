#!/usr/bin/env bash

podman build ./graylog --format docker -t graylog:test

podman pod create -n artemis-graylog-pod

podman run -d --net host --pod=artemis-graylog-pod --name=artemis-mongo mongo:4.2
podman run -d --net host --pod=artemis-graylog-pod -e "http.host=0.0.0.0" -e "discovery.type=single-node" -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" --name=artemis-elasticsearch docker.elastic.co/elasticsearch/elasticsearch-oss:7.10.0
podman run -d --net host --pod=artemis-graylog-pod -e GRAYLOG_HTTP_EXTERNAL_URI="http://localhost:9000/" -e GRAYLOG_MONGODB_URI="mongodb://localhost:27017/graylog" -e GRAYLOG_ELASTICSEARCH_HOSTS="http://localhost:9200/" --name=artemis-graylog localhost/graylog:test

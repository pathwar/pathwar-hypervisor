# This image contains fig
FROM ubuntu:trusty

# Install dependencies
RUN apt-get update \
 && apt-get upgrade -yq \
 && apt-get install -yq python-pip python2.7 git sudo curl s3cmd docker.io \
 && apt-get clean

# Prepare hypervisor workspace
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY requirements.txt /usr/src/app/
RUN pip install -r requirements.txt
COPY . /usr/src/app
ENTRYPOINT []
CMD ["python", "daemon/hypervisor.py"]

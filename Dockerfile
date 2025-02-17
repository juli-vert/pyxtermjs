FROM ubuntu:jammy
RUN apt-get update && apt-get install -y python3 python3-pip
RUN apt-get install -y apt-transport-https ca-certificates curl software-properties-common
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
RUN add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
RUN apt-cache policy docker-ce && apt-get install -y docker-ce
COPY requirements.in .
COPY requirements.txt .
RUN pip3 install -r requirements.txt
WORKDIR /app
COPY pyxtermjs/* .
ENTRYPOINT [ "python3", "app.py" ]

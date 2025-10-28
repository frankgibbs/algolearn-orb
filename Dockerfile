FROM python:3.12

# Set timezone to America/Los_Angeles (Pacific Time)
ENV TZ=America/Los_Angeles
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install all system dependencies in one layer
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

ADD IBJts/source/pythonclient /app/IBJts/source/pythonclient
WORKDIR /app/IBJts/source/pythonclient
RUN pip install setuptools wheel
RUN python setup.py install
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
  tar -xvzf ta-lib-0.4.0-src.tar.gz && \
  cd ta-lib/ && \
  ./configure --prefix=/usr && \
  make && \
  make install

RUN rm -R ta-lib ta-lib-0.4.0-src.tar.gz
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Build dashboard
WORKDIR /app/dashboard
RUN npm install && npm run build

# Return to app directory
WORKDIR /app

# Create data directory
RUN mkdir -p /app/data

# Make scripts executable
RUN chmod +x stocks.sh

# Run the ORB strategy service
CMD ["./stocks.sh"]
